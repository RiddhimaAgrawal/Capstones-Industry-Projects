import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from . import metrics
from .db import init_db
from .metering import USAGE_LIST, record_event
from .redis_client import get_redis
from .routers import analyze, auth, billing, keys, usage, webhook_endpoints

DESCRIPTION = """
**Text Analysis API as a product.** Create an account, generate an API key, call the
endpoints with `X-API-Key`, watch your usage, upgrade to Pro with Stripe.

* Rate limit: Redis token bucket per key (`X-RateLimit-*` headers, `429` + `Retry-After`)
* Quota: monthly per account (`X-Quota-*` headers)
* Events: register webhooks for `quota.warning`, `quota.exceeded`, `plan.changed`, `key.created`, `key.revoked`
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Text Analysis API Platform", version="1.0.0", description=DESCRIPTION, lifespan=lifespan)

for r in (auth.router, keys.router, usage.router, webhook_endpoints.router, billing.router, analyze.router):
    app.include_router(r)


@app.middleware("http")
async def metering_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    latency = time.perf_counter() - start

    route = request.scope.get("route")
    endpoint = route.path if route else request.url.path
    ctx = getattr(request.state, "api_ctx", None)

    for k, v in getattr(request.state, "rl_headers", {}).items():
        response.headers[k] = v

    if endpoint not in ("/metrics", "/healthz"):
        plan = ctx.plan.name if ctx else "none"
        metrics.REQUESTS.labels(endpoint, plan, str(response.status_code)).inc()
        metrics.LATENCY.labels(endpoint).observe(latency)

    if ctx is not None:  # a product call from an authenticated key -> meter it
        try:
            record_event(get_redis(), customer_id=ctx.customer.id, api_key_id=ctx.key.id,
                         endpoint=endpoint, status=response.status_code, latency_ms=latency * 1000)
        except Exception:
            pass  # never fail a customer request because metering is down
    return response


@app.get("/healthz", tags=["Ops"])
def healthz():
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics():
    try:
        metrics.QUEUE_DEPTH.set(get_redis().llen(USAGE_LIST))
    except Exception:
        pass
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/portal", include_in_schema=False)
def portal():
    return FileResponse(Path(__file__).parent / "static" / "portal.html")
