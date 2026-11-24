import json
import time

import fakeredis
import pytest

from app import analysis, redis_client
from app.db import SessionLocal
from app.models import ApiKey, Customer, UsageDaily, WebhookDelivery
from app.ratelimit import TokenBucketLimiter
from app.tasks import aggregate_usage
from app.webhooks import signature_header, sign


# ---------- product API ----------
def test_sentiment_endpoint(client, account):
    _, key = account
    r = client.post("/v1/analyze/sentiment", json={"text": "I absolutely loved this wonderful film"}, headers={"X-API-Key": key})
    assert r.status_code == 200 and r.json()["label"] == "positive"
    r = client.post("/v1/analyze/sentiment", json={"text": "This was not good, a boring waste of time"}, headers={"X-API-Key": key})
    assert r.json()["label"] == "negative"


def test_stats_and_keywords(client, account):
    _, key = account
    h = {"X-API-Key": key}
    s = client.post("/v1/analyze/stats", json={"text": "One two three. Four five!"}, headers=h).json()
    assert s["words"] == 5 and s["sentences"] == 2
    k = client.post("/v1/analyze/keywords", json={"text": "python python api api api rocks", "top_n": 2}, headers=h).json()
    assert k["keywords"][0] == {"word": "api", "count": 3}


# ---------- API keys ----------
def test_missing_and_invalid_key(client):
    assert client.post("/v1/analyze/stats", json={"text": "x"}).status_code == 401
    assert client.post("/v1/analyze/stats", json={"text": "x"}, headers={"X-API-Key": "apk_nope"}).status_code == 401


def test_key_is_hashed_in_db(client, account):
    _, key = account
    db = SessionLocal()
    row = db.query(ApiKey).first()
    assert key not in (row.key_hash, row.prefix) and len(row.key_hash) == 64
    assert key.startswith(row.prefix)
    db.close()


def test_key_listing_never_leaks_secret(client, account):
    headers, key = account
    listing = client.get("/v1/keys", headers=headers).text
    assert key not in listing


def test_revoke_key_takes_effect_immediately(client, account):
    headers, key = account
    assert client.post("/v1/analyze/stats", json={"text": "hi"}, headers={"X-API-Key": key}).status_code == 200
    key_id = client.get("/v1/keys", headers=headers).json()[0]["id"]
    assert client.delete(f"/v1/keys/{key_id}", headers=headers).json()["revoked"] is True
    r = client.post("/v1/analyze/stats", json={"text": "hi"}, headers={"X-API-Key": key})
    assert r.status_code == 401 and "revoked" in r.json()["detail"]


def test_cannot_revoke_someone_elses_key(client, account):
    other = client.post("/v1/auth/register", json={"email": "b@example.com", "password": "supersecret2"}).json()["access_token"]
    headers, _ = account
    key_id = client.get("/v1/keys", headers=headers).json()[0]["id"]
    assert client.delete(f"/v1/keys/{key_id}", headers={"Authorization": "Bearer " + other}).status_code == 404


# ---------- rate limiting ----------
def test_token_bucket_unit():
    lim = TokenBucketLimiter(fakeredis.FakeRedis(decode_responses=True))
    t = 1_000_000
    for _ in range(5):
        assert lim.check("b", rate_per_sec=1, burst=5, now_ms=t).allowed
    denied = lim.check("b", rate_per_sec=1, burst=5, now_ms=t)
    assert not denied.allowed and denied.retry_after_s >= 1
    assert lim.check("b", rate_per_sec=1, burst=5, now_ms=t + 2000).allowed  # 2 tokens refilled
    assert lim.check("b", rate_per_sec=1, burst=5, now_ms=t + 2000).allowed
    assert not lim.check("b", rate_per_sec=1, burst=5, now_ms=t + 2000).allowed


def test_rate_limit_http_429_with_headers(client, account):
    _, key = account
    h = {"X-API-Key": key}
    codes = [client.post("/v1/analyze/stats", json={"text": "hi"}, headers=h).status_code for _ in range(12)]
    assert codes[:10] == [200] * 10          # free plan burst = 10
    assert 429 in codes[10:]
    r = client.post("/v1/analyze/stats", json={"text": "hi"}, headers=h)
    assert r.status_code == 429 and "Retry-After" in r.headers and r.headers["X-RateLimit-Remaining"] == "0"


def test_rate_limits_are_per_key(client, account):
    headers, key1 = account
    key2 = client.post("/v1/keys", json={"name": "second"}, headers=headers).json()["api_key"]
    for _ in range(11):
        client.post("/v1/analyze/stats", json={"text": "hi"}, headers={"X-API-Key": key1})
    assert client.post("/v1/analyze/stats", json={"text": "hi"}, headers={"X-API-Key": key2}).status_code == 200


# ---------- quota + plans ----------
def test_quota_exceeded_and_pro_upgrade_lifts_it(client, account, monkeypatch):
    headers, key = account
    from app.plans import PLANS, Plan
    monkeypatch.setitem(PLANS, "free", Plan("free", rate_per_sec=1000, burst=1000, monthly_quota=5, price_usd=0))
    h = {"X-API-Key": key}
    assert [client.post("/v1/analyze/stats", json={"text": "hi"}, headers=h).status_code for _ in range(5)] == [200] * 5
    r = client.post("/v1/analyze/stats", json={"text": "hi"}, headers=h)
    assert r.status_code == 429 and "quota" in r.json()["detail"].lower()
    assert client.get("/v1/account", headers=headers).json()["usage_this_month"] == 5  # rejected call not counted

    db = SessionLocal()
    db.query(Customer).first().plan = "pro"
    db.commit()
    db.close()
    assert client.post("/v1/analyze/stats", json={"text": "hi"}, headers=h).status_code == 200


# ---------- metering ----------
def test_usage_is_metered_and_aggregated(client, account):
    headers, key = account
    h = {"X-API-Key": key}
    for _ in range(3):
        client.post("/v1/analyze/sentiment", json={"text": "great"}, headers=h)
    client.post("/v1/analyze/stats", json={"text": ""}, headers=h)  # 422 validation error counts as an error
    assert redis_client.get_redis().llen("usage:events") == 4
    assert aggregate_usage() == 4
    assert redis_client.get_redis().llen("usage:events") == 0
    rows = client.get("/v1/usage", headers=headers).json()["rows"]
    by_ep = {r["endpoint"]: r for r in rows}
    assert by_ep["/v1/analyze/sentiment"]["requests"] == 3
    assert by_ep["/v1/analyze/stats"]["errors"] == 1
    assert aggregate_usage() == 0  # idempotent: nothing left to double-count
    assert client.get("/v1/keys", headers=headers).json()[0]["last_used_at"] is not None


# ---------- webhooks ----------
def test_signature_format():
    body = '{"a":1}'
    header = signature_header("secret", body, timestamp=123)
    assert header == f"t=123,v1={sign('secret', 123, body)}"


def test_webhook_delivery_signed_and_recorded(client, account, monkeypatch):
    headers, key = account
    sent = {}

    class FakeResp:
        status_code = 200

    def fake_post(url, content, headers, timeout):
        sent.update(url=url, body=content, headers=headers)
        return FakeResp()

    monkeypatch.setattr("app.tasks.httpx.post", fake_post)
    ep = client.post("/v1/webhooks", json={"url": "https://example.com/hook", "events": ["key.created"]}, headers=headers).json()
    client.post("/v1/keys", json={"name": "another"}, headers=headers)   # triggers key.created

    assert sent["url"] == "https://example.com/hook"
    payload = json.loads(sent["body"])
    assert payload["event"] == "key.created"
    t = sent["headers"]["X-Signature"].split(",")[0][2:]
    expected = sign(ep["secret"], int(t), sent["body"])
    assert sent["headers"]["X-Signature"].endswith("v1=" + expected)
    d = client.get(f"/v1/webhooks/{ep['id']}/deliveries", headers=headers).json()
    assert d[0]["status"] == "delivered" and d[0]["response_code"] == 200


def test_webhook_event_filter(client, account, monkeypatch):
    headers, _ = account
    calls = []
    monkeypatch.setattr("app.tasks.httpx.post", lambda *a, **k: calls.append(1) or type("R", (), {"status_code": 200})())
    client.post("/v1/webhooks", json={"url": "https://example.com/h", "events": ["plan.changed"]}, headers=headers)
    client.post("/v1/keys", json={"name": "x"}, headers=headers)  # key.created -> filtered out
    assert calls == []


def test_quota_warning_webhook_fires_once(client, account, monkeypatch):
    headers, key = account
    from app.plans import PLANS, Plan
    monkeypatch.setitem(PLANS, "free", Plan("free", rate_per_sec=1000, burst=1000, monthly_quota=10, price_usd=0))
    events = []
    monkeypatch.setattr("app.tasks.httpx.post",
                        lambda url, content, headers, timeout: events.append(json.loads(content)["event"]) or type("R", (), {"status_code": 200})())
    client.post("/v1/webhooks", json={"url": "https://example.com/h", "events": ["quota.warning", "quota.exceeded"]}, headers=headers)
    for _ in range(13):
        client.post("/v1/analyze/stats", json={"text": "hi"}, headers={"X-API-Key": key})
    assert events.count("quota.warning") == 1 and events.count("quota.exceeded") == 1


def test_webhook_failure_marks_retry(client, account, monkeypatch):
    headers, _ = account
    import httpx

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr("app.tasks.httpx.post", boom)
    monkeypatch.setattr("app.tasks.deliver_webhook.retry", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("retry-scheduled")), raising=False)
    ep = client.post("/v1/webhooks", json={"url": "https://example.com/h"}, headers=headers).json()
    client.post("/v1/keys", json={"name": "y"}, headers=headers)  # eager mode swallows the retry signal
    db = SessionLocal()
    d = db.query(WebhookDelivery).filter_by(endpoint_id=ep["id"]).first()
    assert d.attempts == 1 and d.status == "pending"
    db.close()


# ---------- billing (Stripe mocked) ----------
def _stripe_event(monkeypatch, etype, obj):
    monkeypatch.setattr("app.routers.billing.stripe.Webhook.construct_event",
                        lambda payload, sig, secret: {"type": etype, "data": {"object": obj}})


def test_stripe_checkout_completed_upgrades_plan(client, account, monkeypatch):
    headers, _ = account
    cid = client.get("/v1/account", headers=headers)  # ensure exists
    db = SessionLocal(); customer_id = db.query(Customer).first().id; db.close()
    _stripe_event(monkeypatch, "checkout.session.completed",
                  {"client_reference_id": str(customer_id), "customer": "cus_123", "subscription": "sub_123"})
    assert client.post("/v1/billing/stripe-webhook", content=b"{}", headers={"Stripe-Signature": "x"}).status_code == 200
    assert client.get("/v1/account", headers=headers).json()["plan"] == "pro"

    _stripe_event(monkeypatch, "customer.subscription.deleted", {"customer": "cus_123", "id": "sub_123", "status": "canceled"})
    client.post("/v1/billing/stripe-webhook", content=b"{}", headers={"Stripe-Signature": "x"})
    assert client.get("/v1/account", headers=headers).json()["plan"] == "free"


def test_stripe_webhook_rejects_bad_signature(client):
    r = client.post("/v1/billing/stripe-webhook", content=b"{}", headers={"Stripe-Signature": "bad"})
    assert r.status_code == 400


def test_checkout_creates_session(client, account, monkeypatch):
    headers, _ = account
    monkeypatch.setattr("app.routers.billing.stripe.Customer.create", lambda **k: type("C", (), {"id": "cus_1"})())
    monkeypatch.setattr("app.routers.billing.stripe.checkout.Session.create", lambda **k: type("S", (), {"url": "https://checkout.stripe.test/x"})())
    r = client.post("/v1/billing/checkout", headers=headers)
    assert r.json()["checkout_url"].startswith("https://checkout.stripe.test")


# ---------- auth / ops ----------
def test_duplicate_register_and_bad_login(client, account):
    assert client.post("/v1/auth/register", json={"email": "dev@example.com", "password": "supersecret1"}).status_code == 409
    assert client.post("/v1/auth/login", json={"email": "dev@example.com", "password": "wrongwrong"}).status_code == 401
    assert client.post("/v1/auth/login", json={"email": "dev@example.com", "password": "supersecret1"}).status_code == 200


def test_metrics_endpoint(client, account):
    _, key = account
    client.post("/v1/analyze/stats", json={"text": "hi"}, headers={"X-API-Key": key})
    body = client.get("/metrics").text
    assert "api_requests_total" in body and 'endpoint="/v1/analyze/stats"' in body
    assert "api_request_latency_seconds_bucket" in body


def test_openapi_and_portal(client):
    spec = client.get("/openapi.json").json()
    assert "/v1/analyze/sentiment" in spec["paths"]
    assert client.get("/portal").status_code == 200
    assert client.get("/healthz").json() == {"status": "ok"}


def test_sentiment_negation_unit():
    assert analysis.sentiment("not good")["label"] == "negative"
    assert analysis.sentiment("")["label"] == "neutral"
