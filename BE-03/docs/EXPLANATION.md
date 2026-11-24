# What the code does, end to end

## The life of one API call
1. Client sends `POST /v1/analyze/sentiment` with header `X-API-Key: apk_...`.
2. `api_key_guard` (app/deps.py) runs before the endpoint:
   1. Computes `HMAC-SHA256(pepper, key)` and looks it up in `api_keys`. Missing/unknown/revoked → `401`.
   2. Loads the customer's plan (free/pro).
   3. **Rate limit:** calls the Redis Lua token bucket for `rl:key:<id>`. Bucket refills at `rate_per_sec`, holds up to `burst`. Empty → `429` with `Retry-After`.
   4. **Quota:** `INCR quota:<customer>:<YYYYMM>`. Above plan quota → undo the increment, `429`. Crossing 80% fires `quota.warning`; first rejection fires `quota.exceeded` (webhooks).
3. The endpoint runs the text-analysis function and returns JSON.
4. The middleware (app/main.py) adds `X-RateLimit-*` / `X-Quota-*` headers, updates Prometheus counters/histograms, and `RPUSH`es a tiny JSON usage event to Redis (never fails the request if Redis metering breaks).
5. Every 15 s Celery beat runs `aggregate_usage`: pops events in batches of 1000, groups them by (key, day, endpoint), upserts counts/errors/429s/latency into `usage_daily`, and updates `last_used_at`. If the DB write fails the events are pushed back.
6. `GET /v1/usage` reads the rollups; `GET /v1/account` shows the live monthly counter.

## File by file
| File | Purpose |
|------|---------|
| `config.py` | Reads env vars (DB, Redis, secrets, Stripe). |
| `db.py`, `models.py` | SQLAlchemy engine/session; tables `customers`, `api_keys`, `usage_daily`, `webhook_endpoints`, `webhook_deliveries`. |
| `security.py` | Key generation (`apk_` + 256-bit random), HMAC hashing, scrypt password hashing, JWT login tokens. |
| `plans.py` | Free/Pro limits in one place. |
| `ratelimit.py` | Token-bucket Lua script + Python wrapper. Atomic read-refill-consume-write. |
| `metering.py` | Event format + Redis list + monthly counter key. |
| `tasks.py` | Celery: `aggregate_usage`, `deliver_webhook` (5 retries, exponential backoff). |
| `webhooks.py` | Creates delivery rows and signs payloads: header `X-Signature: t=<ts>,v1=HMAC(secret, "<ts>.<body>")`. |
| `metrics.py` | Prometheus metrics (requests, latency, 429s, quota rejections, auth failures, queue depth). |
| `analysis.py` | Lexicon-based sentiment with negation + intensifiers, text stats, keywords. |
| `routers/auth.py` | Register/login/account. |
| `routers/keys.py` | Create (plaintext once), list (no secrets), revoke (instant). Max 5 active keys. |
| `routers/usage.py` | Daily usage query. |
| `routers/webhook_endpoints.py` | Register endpoints, filter by event, delivery log. |
| `routers/billing.py` | Stripe Checkout, Customer Portal, and the signed webhook that sets the plan. |
| `routers/analyze.py` | The product endpoints. |
| `static/portal.html` | Developer portal UI (signup, keys, try-it, usage, upgrade). |

## Security choices
* API keys never stored in plaintext; DB leak alone cannot reveal them (pepper in env).
* Passwords: scrypt with per-user salt. Login tokens: signed JWT (12 h).
* Tenant isolation: every key/webhook/usage query is filtered by the authenticated customer.
* Stripe webhook signature verified; plan never changes from the client.
* Webhook payloads signed so customers can verify they came from you.

## Stripe flow
Portal → `POST /v1/billing/checkout` → Stripe-hosted page → payment → Stripe sends `checkout.session.completed` to
`/v1/billing/stripe-webhook` → signature checked → customer set to `pro` → `plan.changed` event emitted.
Cancellation → `customer.subscription.deleted` → back to `free`.
