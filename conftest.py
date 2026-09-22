import os

import psycopg
import pytest

DATABASE_URL = os.environ["DATABASE_URL"]

from fastapi.testclient import TestClient

from api import app  # noqa:


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE items, receipts, categories RESTART IDENTITY CASCADE")
    yield


@pytest.fixture
def make_receipt(client):
    def _make(shop="Тест", total=100, items=None):
        if items is None:
            items = [{"name": "товар", "price": 100}]
        response = client.post(
            "/receipts", json={"shop": shop, "total": total, "items": items}
        )
        assert response.status_code == 201
        return response.json()

    return _make
