"""Stripe (test mode) billing: Checkout to upgrade, Portal to manage, and a
signature-verified webhook that is the ONLY thing allowed to change a plan."""
import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from .. import metrics
from ..config import settings
from ..db import get_db
from ..deps import current_customer
from ..models import Customer
from ..webhooks import emit_event

router = APIRouter(prefix="/v1/billing", tags=["Billing"])


def _require_stripe():
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(503, "Stripe is not configured (set STRIPE_SECRET_KEY, see README)")
    stripe.api_key = settings.STRIPE_SECRET_KEY


@router.post("/checkout", summary="Start a Stripe Checkout session to upgrade to Pro")
def checkout(c: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    _require_stripe()
    if c.plan == "pro":
        raise HTTPException(400, "Already on the Pro plan")
    if not c.stripe_customer_id:
        sc = stripe.Customer.create(email=c.email, metadata={"customer_id": str(c.id)})
        c.stripe_customer_id = sc.id
        db.commit()
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=c.stripe_customer_id,
        client_reference_id=str(c.id),
        line_items=[{"price": settings.STRIPE_PRO_PRICE_ID, "quantity": 1}],
        success_url=f"{settings.PUBLIC_URL}/portal?upgraded=1",
        cancel_url=f"{settings.PUBLIC_URL}/portal?cancelled=1",
    )
    return {"checkout_url": session.url}


@router.post("/portal", summary="Open the Stripe customer portal (cancel / update card)")
def portal(c: Customer = Depends(current_customer)):
    _require_stripe()
    if not c.stripe_customer_id:
        raise HTTPException(400, "No billing account yet")
    s = stripe.billing_portal.Session.create(customer=c.stripe_customer_id, return_url=f"{settings.PUBLIC_URL}/portal")
    return {"portal_url": s.url}


def _set_plan(db: Session, customer: Customer, plan: str, subscription_id: str | None):
    changed = customer.plan != plan
    customer.plan = plan
    customer.stripe_subscription_id = subscription_id
    db.commit()
    if changed:
        emit_event(db, customer.id, "plan.changed", {"plan": plan})


@router.post("/stripe-webhook", include_in_schema=False)
async def stripe_webhook(request: Request, stripe_signature: str = Header(default=""), db: Session = Depends(get_db)):
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET)
    except Exception:
        raise HTTPException(400, "Invalid Stripe signature")

    etype = event["type"]
    obj = event["data"]["object"]
    metrics.WEBHOOK_EVENTS.labels(etype).inc()

    if etype == "checkout.session.completed":
        customer = db.get(Customer, int(obj.get("client_reference_id") or 0))
        if customer:
            customer.stripe_customer_id = obj.get("customer") or customer.stripe_customer_id
            _set_plan(db, customer, "pro", obj.get("subscription"))
    elif etype in ("customer.subscription.updated", "customer.subscription.deleted"):
        customer = db.query(Customer).filter_by(stripe_customer_id=obj.get("customer")).one_or_none()
        if customer:
            active = obj.get("status") in ("active", "trialing") and etype != "customer.subscription.deleted"
            _set_plan(db, customer, "pro" if active else "free", obj.get("id") if active else None)
    elif etype == "invoice.payment_failed":
        customer = db.query(Customer).filter_by(stripe_customer_id=obj.get("customer")).one_or_none()
        if customer:
            emit_event(db, customer.id, "plan.changed", {"plan": customer.plan, "payment_failed": True})
    return {"received": True}
