import os

# Must be set before the app is imported.
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["CELERY_ALWAYS_EAGER"] = "1"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_dummy"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_dummy"
os.environ["STRIPE_PRO_PRICE_ID"] = "price_dummy"

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app import redis_client
from app.db import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_state():
    redis_client.set_redis(fakeredis.FakeRedis(decode_responses=True))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def account(client):
    """A registered customer: returns (auth_headers, api_key_plaintext)."""
    r = client.post("/v1/auth/register", json={"email": "dev@example.com", "password": "supersecret1"})
    assert r.status_code == 201
    headers = {"Authorization": "Bearer " + r.json()["access_token"]}
    key = client.post("/v1/keys", json={"name": "test"}, headers=headers).json()["api_key"]
    return headers, key
