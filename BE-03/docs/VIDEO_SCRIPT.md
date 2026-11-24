# Demo video script (~8–10 min) — record with OBS Studio / Loom / Zoom

Tip: `docker compose up --build` running before you record. Open four tabs: /portal, /docs, Prometheus :9090, your terminal.

| Time | Show | Say |
|------|------|-----|
| 0:00 | Title slide | "This is an API sold as a product: keys, limits, billing, webhooks, docs." |
| 0:40 | Architecture diagram | Walk left→right: FastAPI, Redis, Postgres, Celery, Stripe, Prometheus. |
| 1:30 | /portal | Sign up. Create key; point out it is shown once. |
| 2:30 | Try it box | Run sentiment on a positive and a negative sentence. Show `X-RateLimit-Remaining` dropping. |
| 3:30 | Hammer the button | Get `429` + `Retry-After`. Explain token bucket (burst 10, 0.5/s). |
| 4:30 | Terminal | `python scripts/load_test.py --key ... --n 200` → 11×200 and 189×429. |
| 5:15 | Portal usage table | Wait ≤15 s; show Celery-aggregated rows. Explain Redis list → Celery → Postgres. |
| 6:00 | Revoke key | Re-call API → 401 "revoked". |
| 6:30 | Stripe | Upgrade → test card 4242… → plan flips to Pro; limits jump to 100 burst / 20 per s. |
| 7:30 | Webhooks | Register a https://webhook.site URL; create a key; show the signed POST + signature header. |
| 8:15 | /metrics + Prometheus | Query `rate(api_requests_total[1m])`, `api_rate_limited_total`. |
| 8:45 | /docs + SDK | Show Swagger; run `generate_sdks.sh`; show generated python client. |
| 9:15 | Tests | `pytest -q` → 24 passed. |
| 9:40 | Close | Next steps: migrations, key cache, usage-based Stripe billing. |

## 10-minute presentation talk track
Use the PowerPoint (`BE-03_Presentation.pptx`): each slide has speaker notes.
