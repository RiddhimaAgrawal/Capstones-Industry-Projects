"""FastAPI dependencies: JWT auth for the dashboard, API-key auth + rate limit +
quota for the product endpoints."""
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from . import metrics
from .db import get_db
from .metering import month_key
from .models import ApiKey, Customer
from .plans import Plan, get_plan
from .ratelimit import TokenBucketLimiter
from .redis_client import get_redis
from .security import decode_token, hash_api_key
from .webhooks import emit_event

_limiters: dict[int, TokenBucketLimiter] = {}


def get_limiter() -> TokenBucketLimiter:
    r = get_redis()
    if id(r) not in _limiters:
        _limiters.clear()
        _limiters[id(r)] = TokenBucketLimiter(r)
    return _limiters[id(r)]


# ---------- dashboard auth (JWT) ----------
def current_customer(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> Customer:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    cid = decode_token(authorization[7:])
    customer = db.get(Customer, cid) if cid else None
    if customer is None:
        raise HTTPException(401, "Invalid or expired token")
    return customer


# ---------- product API auth ----------
@dataclass
class ApiContext:
    customer: Customer
    key: ApiKey
    plan: Plan


def api_key_guard(request: Request, x_api_key: str = Header(default="", alias="X-API-Key"),
                  db: Session = Depends(get_db)) -> ApiContext:
    if not x_api_key:
        metrics.AUTH_FAILURES.labels("missing").inc()
        raise HTTPException(401, "Missing X-API-Key header")

    key = db.query(ApiKey).filter_by(key_hash=hash_api_key(x_api_key)).one_or_none()
    if key is None:
        metrics.AUTH_FAILURES.labels("invalid").inc()
        raise HTTPException(401, "Invalid API key")
    if key.revoked_at is not None:
        metrics.AUTH_FAILURES.labels("revoked").inc()
        raise HTTPException(401, "API key has been revoked")

    customer = db.get(Customer, key.customer_id)
    plan = get_plan(customer.plan)
    ctx = ApiContext(customer, key, plan)
    request.state.api_ctx = ctx  # lets the middleware meter this call (even if we reject it below)

    # 1) Rate limit (token bucket, per key)
    res = get_limiter().check(f"key:{key.id}", plan.rate_per_sec, plan.burst)
    request.state.rl_headers = {
        "X-RateLimit-Limit": str(res.limit),
        "X-RateLimit-Remaining": str(res.remaining),
    }
    if not res.allowed:
        metrics.RATE_LIMITED.labels(plan.name).inc()
        raise HTTPException(429, "Rate limit exceeded",
                            headers={**request.state.rl_headers, "Retry-After": str(res.retry_after_s)})

    # 2) Monthly quota (per customer, shared by all their keys)
    r = get_redis()
    mk = month_key(customer.id)
    used = r.incr(mk)
    if used == 1:
        r.expire(mk, 60 * 60 * 24 * 40)
    request.state.rl_headers.update({"X-Quota-Limit": str(plan.monthly_quota),
                                     "X-Quota-Remaining": str(max(0, plan.monthly_quota - used))})
    warn_at = int(plan.monthly_quota * 0.8)
    if used == warn_at:
        emit_event(db, customer.id, "quota.warning", {"used": used, "quota": plan.monthly_quota, "percent": 80})
    if used > plan.monthly_quota:
        r.decr(mk)  # rejected calls don't consume quota
        metrics.QUOTA_EXCEEDED.labels(plan.name).inc()
        if r.set(f"quota_exceeded_sent:{mk}", 1, nx=True, ex=60 * 60 * 24 * 40):
            emit_event(db, customer.id, "quota.exceeded", {"quota": plan.monthly_quota})
        raise HTTPException(429, "Monthly quota exceeded. Upgrade your plan to continue.",
                            headers={**request.state.rl_headers, "Retry-After": "3600"})
    return ctx
