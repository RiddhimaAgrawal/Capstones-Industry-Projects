# Individual reflection: BE-03 API Platform with Rate Limiting, Billing and Developer Portal

## What I owned
I ran the complete API platform on my own machine: the FastAPI service, PostgreSQL, Redis, the Celery worker and beat scheduler, and Prometheus, started together with Docker Compose. I worked through the developer flow myself (sign up, create an API key, call the text-analysis endpoints, hit the rate limit, watch usage appear), ran the 24 automated tests, recorded the working demo video, wrote the reflection and prepared the repository for submission under my own name. I also took responsibility for being able to explain how each piece works: key hashing, the token bucket, metering, plans and Stripe webhooks.

## What I learned
- **An API can be a product.** Keys, limits, metering, plans and billing are what turn an endpoint into something you can sell, and each needs its own design.
- **Never store raw API keys.** Keys are shown once and stored only as an HMAC-SHA256 hash with a server pepper. They are random and long, so a fast hash is safe and keeps lookups cheap. Revocation is then just a flag.
- **Rate limiting has to be atomic.** A token bucket implemented as a Lua script in Redis runs as one step, so it stays correct with many API workers. It gives both a burst allowance and a sustained rate, and it returns 429 with `Retry-After`.
- **Keep metering off the hot path.** The request only pushes one event to Redis. Celery batches those events into PostgreSQL usage tables, so a slow database never slows an API call. Quota uses a separate live counter.
- **Trust billing only through signed webhooks.** A plan changes to Pro only when a Stripe webhook arrives with a valid signature, never because the browser says payment succeeded.
- **Outgoing webhooks need signing and retries.** Customers must be able to verify who sent an event, and a failed delivery should be retried.
- **Observability.** Prometheus counters and histograms show request counts, 429s and latency, so the system can be monitored rather than guessed at.
- **Test results need honest labels.** My load figures came from one machine, so they show the limiter is correct under concurrency but are not a capacity claim.

## Hardest problem and how I handled it
The hardest design problem was making limits correct under concurrent requests without slowing every call. A naive read-then-write counter lets parallel requests slip past the limit, and writing every call straight to the database would make the database the bottleneck. The platform solves both: an atomic Lua token bucket in Redis for the limit, and an event queue drained by Celery for metering. Seeing the tests confirm it (a free key getting about 10 successes and the rest 429 in a burst, and all metered events aggregating exactly) made the reasoning concrete for me.

## What I would do next
- Use proper database migrations (Alembic) instead of `create_all`.
- Cache API key lookups in Redis and move to Redis Cluster for scale.
- Add per-endpoint cost weights and Stripe usage-based billing.
- Rate-limit the sign-up and login endpoints and add email verification.
- Add Grafana dashboards, and evaluate the sentiment model on IMDB or Sentiment140 to report a real accuracy.
