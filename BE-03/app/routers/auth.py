from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from .. import metrics
from ..db import get_db
from ..deps import current_customer
from ..metering import month_key
from ..models import Customer
from ..plans import get_plan
from ..redis_client import get_redis
from ..security import create_token, hash_password, verify_password

router = APIRouter(prefix="/v1", tags=["Account"])


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/auth/register", response_model=TokenOut, status_code=201, summary="Create an account")
def register(body: Credentials, db: Session = Depends(get_db)):
    if db.query(Customer).filter_by(email=body.email.lower()).first():
        raise HTTPException(409, "Email already registered")
    c = Customer(email=body.email.lower(), password_hash=hash_password(body.password))
    db.add(c)
    db.commit()
    metrics.SIGNUPS.inc()
    return TokenOut(access_token=create_token(c.id))


@router.post("/auth/login", response_model=TokenOut, summary="Log in and get a dashboard token")
def login(body: Credentials, db: Session = Depends(get_db)):
    c = db.query(Customer).filter_by(email=body.email.lower()).first()
    if c is None or not verify_password(body.password, c.password_hash):
        raise HTTPException(401, "Wrong email or password")
    return TokenOut(access_token=create_token(c.id))


@router.get("/account", summary="Current account, plan and live quota usage")
def account(c: Customer = Depends(current_customer)):
    plan = get_plan(c.plan)
    used = int(get_redis().get(month_key(c.id)) or 0)
    return {
        "email": c.email,
        "plan": plan.name,
        "limits": {"rate_per_sec": plan.rate_per_sec, "burst": plan.burst, "monthly_quota": plan.monthly_quota},
        "usage_this_month": used,
        "quota_remaining": max(0, plan.monthly_quota - used),
    }
