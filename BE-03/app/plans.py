"""Plan catalogue. `rate_per_sec` is the sustained token-bucket refill rate and
`burst` is the bucket capacity. `monthly_quota` is the hard monthly cap."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    name: str
    rate_per_sec: float
    burst: int
    monthly_quota: int
    price_usd: int


PLANS = {
    "free": Plan("free", rate_per_sec=0.5, burst=10, monthly_quota=1_000, price_usd=0),
    "pro": Plan("pro", rate_per_sec=20.0, burst=100, monthly_quota=100_000, price_usd=29),
}


def get_plan(name: str) -> Plan:
    return PLANS.get(name, PLANS["free"])
