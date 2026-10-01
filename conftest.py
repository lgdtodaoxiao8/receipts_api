import os

import psycopg
import pytest
import redis
from fastapi.testclient import TestClient

DATABASE_URL = os.environ["DATABASE_URL"]

REDIS_URL = os.environ["REDIS_URL"]

from api import app

redis_client = redis.Redis.from_url(REDIS_URL)


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_db():
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE items, receipts, categories RESTART IDENTITY CASCADE")
    yield


@pytest.fixture(autouse=True)
def clean_cache():
    redis_client.flushdb()


@pytest.fixture
def make_receipt(client: TestClient):
    def _make(shop="Тест", total=100, items=None):

        if items is None:
            items = [{"name": "товар", "price": 100}]

        response = client.post(
            "/receipts", json={"shop": shop, "total": total, "items": items}
        )
        assert response.status_code == 201
        return response.json()

    return _make


@pytest.fixture
def make_category(client: TestClient):
    def _make(name="Тест"):
        response = client.post(
            "/categories",
            json={"name": name},
        )

        assert response.status_code == 201
        return response.json()

    return _make
