from collections.abc import Iterator

import psycopg
import pytest
import redis
from fastapi.testclient import TestClient

from api import app
from config import DATABASE_URL, REDIS_URL

redis_client = redis.Redis.from_url(REDIS_URL)


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_db():
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE items, receipts, categories, users RESTART IDENTITY CASCADE"
        )
    yield


@pytest.fixture(autouse=True)
def clean_cache():
    redis_client.flushdb()


@pytest.fixture()
def create_user(client: TestClient, clean_db):
    def _make(
        email: str | None = "example@mail.com",
        password: str | None = "password-example",
    ):

        payload = {"email": email, "password": password}

        assert client.post("/auth/register", json=payload).status_code == 201

        login_response = client.post("/auth/login", json=payload)

        assert login_response.status_code == 200

        token = login_response.json()["access_token"]

        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture(autouse=True)
def default_user(client: TestClient, create_user):
    client.headers.update(create_user())
    yield
    client.headers.pop("Authorization", None)


@pytest.fixture
def make_receipt(client: TestClient):
    def _make(shop="Тест", total=100, items=None, purchased_at=None):

        if items is None:
            items = [{"name": "товар", "price": 100}]

        response = client.post(
            "/receipts",
            json={
                "shop": shop,
                "total": total,
                "items": items,
                "purchased_at": purchased_at,
            },
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
