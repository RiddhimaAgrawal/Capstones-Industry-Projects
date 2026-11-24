"""Celery jobs: usage aggregation (periodic) and webhook delivery (retrying)."""
import json
from collections import defaultdict
from datetime import datetime, timezone

import httpx

from .celery_app import celery
from .db import SessionLocal
from .metering import USAGE_LIST
from .models import ApiKey, UsageDaily, WebhookDelivery, WebhookEndpoint
from .redis_client import get_redis
from .webhooks import signature_header

BATCH = 1000


@celery.task(name="app.tasks.aggregate_usage")
def aggregate_usage() -> int:
    """Drain the Redis event list and upsert daily rollups. Returns events processed."""
    r = get_redis()
    processed = 0
    while True:
        raw = r.lpop(USAGE_LIST, BATCH)
        if not raw:
            break
        try:
            _apply(raw)
            processed += len(raw)
        except Exception:
            r.rpush(USAGE_LIST, *raw)  # put them back so nothing is lost
            raise
    return processed


def _apply(raw_events: list[str]) -> None:
    groups = defaultdict(lambda: {"requests": 0, "errors": 0, "rl": 0, "lat": 0.0, "last": None})
    for raw in raw_events:
        ev = json.loads(raw)
        ts = datetime.fromisoformat(ev["t"])
        g = groups[(ev["c"], ev["k"], ts.date(), ev["e"])]
        g["requests"] += 1
        g["errors"] += 1 if ev["s"] >= 400 else 0
        g["rl"] += 1 if ev["s"] == 429 else 0
        g["lat"] += ev["l"]
        g["last"] = ts if g["last"] is None or ts > g["last"] else g["last"]

    db = SessionLocal()
    try:
        for (cid, kid, day, endpoint), g in groups.items():
            row = db.query(UsageDaily).filter_by(api_key_id=kid, day=day, endpoint=endpoint).one_or_none()
            if row is None:
                row = UsageDaily(customer_id=cid, api_key_id=kid, day=day, endpoint=endpoint,
                                 requests=0, errors=0, rate_limited=0, total_latency_ms=0.0)
                db.add(row)
            row.requests += g["requests"]
            row.errors += g["errors"]
            row.rate_limited += g["rl"]
            row.total_latency_ms += g["lat"]
            key = db.get(ApiKey, kid)
            if key and (key.last_used_at is None or key.last_used_at.replace(tzinfo=timezone.utc) < g["last"]):
                key.last_used_at = g["last"]
        db.commit()
    finally:
        db.close()


@celery.task(bind=True, name="app.tasks.deliver_webhook", max_retries=5)
def deliver_webhook(self, delivery_id: int) -> str:
    db = SessionLocal()
    try:
        d = db.get(WebhookDelivery, delivery_id)
        if d is None:
            return "missing"
        ep = db.get(WebhookEndpoint, d.endpoint_id)
        d.attempts += 1
        try:
            resp = httpx.post(
                ep.url,
                content=d.payload,
                headers={"Content-Type": "application/json",
                         "X-Signature": signature_header(ep.secret, d.payload),
                         "X-Event": d.event},
                timeout=5.0,
            )
            d.response_code = resp.status_code
            ok = 200 <= resp.status_code < 300
        except httpx.HTTPError:
            ok = False
        if ok:
            d.status = "delivered"
            db.commit()
            return "delivered"
        d.status = "failed" if d.attempts > self.max_retries else "pending"
        db.commit()
        if d.attempts <= self.max_retries:
            raise self.retry(countdown=min(2 ** d.attempts * 5, 600))
        return "failed"
    finally:
        db.close()
