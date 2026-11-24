import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_customer
from ..models import Customer, WebhookDelivery, WebhookEndpoint
from ..webhooks import EVENTS

router = APIRouter(prefix="/v1/webhooks", tags=["Webhooks"])


class EndpointCreate(BaseModel):
    url: HttpUrl
    events: list[str] = Field(default=["*"], description=f"Subset of {EVENTS} or ['*']")


@router.post("", status_code=201, summary="Register a webhook endpoint")
def create_endpoint(body: EndpointCreate, c: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    bad = [e for e in body.events if e != "*" and e not in EVENTS]
    if bad:
        raise HTTPException(422, f"Unknown events: {bad}. Valid: {EVENTS}")
    ep = WebhookEndpoint(customer_id=c.id, url=str(body.url), secret="whsec_" + secrets.token_hex(16),
                         events=",".join(body.events))
    db.add(ep)
    db.commit()
    return {"id": ep.id, "url": ep.url, "events": body.events, "secret": ep.secret,
            "verify": "Compute HMAC-SHA256(secret, f'{t}.{raw_body}') and compare with v1 in the X-Signature header."}


@router.get("", summary="List webhook endpoints")
def list_endpoints(c: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    return [{"id": e.id, "url": e.url, "events": e.events.split(","), "active": e.active}
            for e in db.query(WebhookEndpoint).filter_by(customer_id=c.id)]


@router.delete("/{endpoint_id}", summary="Delete a webhook endpoint")
def delete_endpoint(endpoint_id: int, c: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    ep = db.query(WebhookEndpoint).filter_by(id=endpoint_id, customer_id=c.id).one_or_none()
    if ep is None:
        raise HTTPException(404, "Endpoint not found")
    ep.active = False
    db.commit()
    return {"deleted": True}


@router.get("/{endpoint_id}/deliveries", summary="Recent delivery attempts")
def deliveries(endpoint_id: int, c: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    ep = db.query(WebhookEndpoint).filter_by(id=endpoint_id, customer_id=c.id).one_or_none()
    if ep is None:
        raise HTTPException(404, "Endpoint not found")
    rows = db.query(WebhookDelivery).filter_by(endpoint_id=ep.id).order_by(WebhookDelivery.id.desc()).limit(50)
    return [{"id": d.id, "event": d.event, "status": d.status, "attempts": d.attempts,
             "response_code": d.response_code, "created_at": d.created_at} for d in rows]
