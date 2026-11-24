from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_customer
from ..models import Customer, UsageDaily

router = APIRouter(prefix="/v1/usage", tags=["Usage"])


@router.get("", summary="Daily usage for the last N days (aggregated by Celery)")
def usage(days: int = Query(30, ge=1, le=365), c: Customer = Depends(current_customer),
          db: Session = Depends(get_db)):
    since = date.today() - timedelta(days=days - 1)
    rows = (db.query(UsageDaily.day, UsageDaily.endpoint,
                     func.sum(UsageDaily.requests), func.sum(UsageDaily.errors),
                     func.sum(UsageDaily.rate_limited), func.sum(UsageDaily.total_latency_ms))
            .filter(UsageDaily.customer_id == c.id, UsageDaily.day >= since)
            .group_by(UsageDaily.day, UsageDaily.endpoint)
            .order_by(UsageDaily.day).all())
    return {
        "since": since,
        "note": "Aggregates refresh every few seconds; /v1/account shows the live monthly counter.",
        "rows": [{"day": d, "endpoint": e, "requests": int(r), "errors": int(er), "rate_limited": int(rl),
                  "avg_latency_ms": round(lat / r, 2) if r else 0} for d, e, r, er, rl, lat in rows],
        "total_requests": sum(int(r[2]) for r in rows),
    }
