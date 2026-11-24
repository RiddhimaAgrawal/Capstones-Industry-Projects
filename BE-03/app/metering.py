"""Metering: the request path only does a cheap Redis RPUSH. Celery later drains
the list and rolls it up into Postgres (see tasks.aggregate_usage)."""
import json
from datetime import datetime, timezone

USAGE_LIST = "usage:events"


def record_event(r, *, customer_id: int, api_key_id: int, endpoint: str, status: int, latency_ms: float):
    event = {
        "c": customer_id,
        "k": api_key_id,
        "e": endpoint,
        "s": status,
        "l": round(latency_ms, 2),
        "t": datetime.now(timezone.utc).isoformat(),
    }
    r.rpush(USAGE_LIST, json.dumps(event))


def month_key(customer_id: int, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"quota:{customer_id}:{now:%Y%m}"
