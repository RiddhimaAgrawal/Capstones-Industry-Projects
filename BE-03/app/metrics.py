"""Prometheus metrics exposed at /metrics."""
from prometheus_client import Counter, Gauge, Histogram

REQUESTS = Counter("api_requests_total", "API requests", ["endpoint", "plan", "status"])
LATENCY = Histogram("api_request_latency_seconds", "Request latency", ["endpoint"],
                    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5))
RATE_LIMITED = Counter("api_rate_limited_total", "Requests rejected by rate limiter", ["plan"])
QUOTA_EXCEEDED = Counter("api_quota_exceeded_total", "Requests rejected by monthly quota", ["plan"])
AUTH_FAILURES = Counter("api_auth_failures_total", "Missing/invalid/revoked API keys", ["reason"])
SIGNUPS = Counter("api_signups_total", "Customer signups")
WEBHOOK_EVENTS = Counter("api_stripe_webhook_events_total", "Stripe webhook events", ["type"])
QUEUE_DEPTH = Gauge("api_usage_queue_depth", "Un-aggregated metering events in Redis")
