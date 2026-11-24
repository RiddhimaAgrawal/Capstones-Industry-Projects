"""Outgoing webhooks: customers register URLs, we POST signed JSON events."""
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .models import WebhookDelivery, WebhookEndpoint

EVENTS = ["key.created", "key.revoked", "quota.warning", "quota.exceeded", "plan.changed"]


def sign(secret: str, timestamp: int, body: str) -> str:
    msg = f"{timestamp}.{body}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def signature_header(secret: str, body: str, timestamp: int | None = None) -> str:
    ts = timestamp or int(time.time())
    return f"t={ts},v1={sign(secret, ts, body)}"


def emit_event(db: Session, customer_id: int, event: str, data: dict) -> list[int]:
    """Create a delivery row for each matching endpoint and queue the Celery job."""
    from .tasks import deliver_webhook  # local import avoids circularity

    endpoints = db.query(WebhookEndpoint).filter_by(customer_id=customer_id, active=True).all()
    ids = []
    for ep in endpoints:
        if ep.events != "*" and event not in ep.events.split(","):
            continue
        payload = json.dumps({"event": event, "created": datetime.now(timezone.utc).isoformat(), "data": data})
        d = WebhookDelivery(endpoint_id=ep.id, event=event, payload=payload)
        db.add(d)
        db.commit()
        ids.append(d.id)
        deliver_webhook.delay(d.id)
    return ids
