from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_customer
from ..models import ApiKey, Customer
from ..security import generate_api_key
from ..webhooks import emit_event

router = APIRouter(prefix="/v1/keys", tags=["API keys"])

MAX_ACTIVE_KEYS = 5


class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, examples=["production"])


def _view(k: ApiKey) -> dict:
    return {"id": k.id, "name": k.name, "prefix": k.prefix, "created_at": k.created_at,
            "last_used_at": k.last_used_at, "revoked": k.revoked_at is not None}


@router.post("", status_code=201, summary="Create an API key (plaintext shown only once)")
def create_key(body: KeyCreate, c: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    active = db.query(ApiKey).filter_by(customer_id=c.id, revoked_at=None).count()
    if active >= MAX_ACTIVE_KEYS:
        raise HTTPException(400, f"Maximum of {MAX_ACTIVE_KEYS} active keys reached; revoke one first")
    plaintext, prefix, key_hash = generate_api_key()
    k = ApiKey(customer_id=c.id, name=body.name, prefix=prefix, key_hash=key_hash)
    db.add(k)
    db.commit()
    emit_event(db, c.id, "key.created", {"key_id": k.id, "name": k.name, "prefix": prefix})
    return {**_view(k), "api_key": plaintext,
            "warning": "Store this key now. It is hashed in our database and cannot be shown again."}


@router.get("", summary="List your keys (never returns secrets)")
def list_keys(c: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    return [_view(k) for k in db.query(ApiKey).filter_by(customer_id=c.id).order_by(ApiKey.id)]


@router.delete("/{key_id}", summary="Revoke a key immediately")
def revoke_key(key_id: int, c: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    k = db.query(ApiKey).filter_by(id=key_id, customer_id=c.id).one_or_none()
    if k is None:
        raise HTTPException(404, "Key not found")
    if k.revoked_at is None:
        k.revoked_at = datetime.now(timezone.utc)
        db.commit()
        emit_event(db, c.id, "key.revoked", {"key_id": k.id, "prefix": k.prefix})
    return _view(k)
