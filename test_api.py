from datetime import UTC, datetime, timedelta
from decimal import Decimal

import jwt
import pytest
from fastapi.testclient import TestClient

import api
from llm import LLMServiceError, ReceiptParseError
from models import ItemIn, ReceiptIn
from security import SECRET_KEY, create_access_token

valid_token = create_access_token(user_id=1)
replaced = valid_token[:-1] + ("a" if valid_token[-1] != "a" else "b")


def test_ping(client: TestClient):
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_receipt(client: TestClient, make_receipt):

    created = make_receipt(
        shop="Тест",
        total=200,
        items=[
            {"name": "молоко", "price": 100},
            {"name": "хлеб", "price": 100},
        ],
    )

    response = client.get(f"/receipts/{created['id']}")

    assert response.status_code == 200

    data = response.json()

    assert data["shop"] == "Тест"
    assert data["total"] == "200.00"
    assert [(item["name"], item["price"]) for item in data["items"]] == [
        ("молоко", "100.00"),
        ("хлеб", "100.00"),
    ]


def test_get_receipt_not_found(client: TestClient):
    response = client.get("/receipts/999")

    assert response.status_code == 404
    assert "detail" in response.json()


def test_receipts_list(client: TestClient, make_receipt):
    make_receipt(shop="первый")
    make_receipt(shop="второй")

    response = client.get("/receipts")

    assert response.status_code == 200

    shops = [receipt["shop"] for receipt in response.json()]

    assert shops == ["второй", "первый"]


def test_pagination(client: TestClient, make_receipt):

    make_receipt(shop="первый")
    make_receipt(shop="второй")
    make_receipt(shop="третий")

    first_page = client.get(
        "/receipts",
        params={
            "limit": 2,
        },
    )

    assert first_page.status_code == 200
    assert [row["shop"] for row in first_page.json()] == ["третий", "второй"]

    second_page = client.get(
        "/receipts",
        params={
            "limit": 2,
            "offset": 2,
        },
    )

    assert second_page.status_code == 200
    assert [row["shop"] for row in second_page.json()] == ["первый"]


def test_create_receipt(client: TestClient):
    response = client.post(
        "/receipts",
        json={
            "shop": "Тестовый",
            "total": 650,
            "items": [
                {"name": "молоко", "price": 450},
                {"name": "хлеб", "price": 200},
            ],
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["shop"] == "Тестовый"
    assert data["total"] == "650.00"
    assert [item["price"] for item in data["items"]] == ["450.00", "200.00"]
    assert data["purchased_at"] is not None
    assert data["id"] > 0


@pytest.mark.parametrize(
    "payload, expected_loc",
    [
        pytest.param(
            {"items": []},
            ["body", "items"],
            id="empty_items",
        ),
        pytest.param(
            {"items": [{"name": "молоко", "price": "дорого"}]},
            ["body", "items", 0, "price"],
            id="price_not_number",
        ),
        pytest.param(
            {"items": [{"name": "молоко", "price": 0}]},
            ["body", "items", 0, "price"],
            id="zero_price",
        ),
        pytest.param(
            {"items": [{"name": "молоко", "price": -100}]},
            ["body", "items", 0, "price"],
            id="negative_price",
        ),
        pytest.param(
            {"items": [{"name": "   ", "price": 100}]},
            ["body", "items", 0, "name"],
            id="blank_name",
        ),
        pytest.param(
            {
                "total": -100,
                "items": [{"name": "молоко", "price": 100}],
            },
            ["body", "total"],
            id="negative_total",
        ),
        pytest.param(
            {
                "total": "много",
                "items": [{"name": "молоко", "price": 100}],
            },
            ["body", "total"],
            id="total_not_number",
        ),
        pytest.param(
            {"items": [{"name": "молоко", "price": 100, "лишнее": 1}]},
            ["body", "items", 0, "лишнее"],
            id="item_extra_field",
        ),
        pytest.param(
            {
                "items": [{"name": "молоко", "price": 100}],
                "лишнее": 1,
            },
            ["body", "лишнее"],
            id="receipt_extra_field",
        ),
    ],
)
def test_create_receipt_invalid(client: TestClient, payload, expected_loc):
    response = client.post("/receipts", json=payload)

    assert response.status_code == 422
    assert len(response.json()["detail"]) == 1
    assert response.json()["detail"][0]["loc"] == expected_loc


@pytest.mark.parametrize(
    "params, expected_loc",
    [
        pytest.param(
            {"limit": 0},
            ["query", "limit"],
            id="limit_zero",
        ),
        pytest.param(
            {"limit": 101},
            ["query", "limit"],
            id="limit_too_big",
        ),
        pytest.param(
            {"offset": -1},
            ["query", "offset"],
            id="negative_offset",
        ),
    ],
)
def test_list_receipts_invalid_params(client: TestClient, params, expected_loc):
    response = client.get("/receipts", params=params)

    assert response.status_code == 422
    assert len(response.json()["detail"]) == 1
    assert response.json()["detail"][0]["loc"] == expected_loc


@pytest.mark.parametrize(
    "params",
    [
        pytest.param(
            {"limit": 1},
            id="limit_min",
        ),
        pytest.param(
            {"limit": 100},
            id="limit_max",
        ),
        pytest.param(
            {"offset": 0},
            id="offset_zero",
        ),
    ],
)
def test_list_receipts_valid_params(client: TestClient, params):
    response = client.get("/receipts", params=params)

    assert response.status_code == 200


@pytest.mark.parametrize(
    "total, expected_discrepancy",
    [
        pytest.param(650, "0.00", id="total_match"),
        pytest.param(1000, "-350.00", id="total_greater"),
        pytest.param(500, "150.00", id="total_less"),
    ],
)
def test_receipt_discrepancy(
    client: TestClient, make_receipt, total, expected_discrepancy
):
    created = make_receipt(
        total=total,
        items=[
            {"name": "молоко", "price": 450},
            {"name": "хлеб", "price": 200},
        ],
    )

    response = client.get(f"/receipts/{created['id']}")

    assert response.status_code == 200

    data = response.json()

    assert data["calculated_total"] == "650.00"
    assert data["discrepancy"] == expected_discrepancy


def test_receipt_discrepancy_no_totals(client: TestClient):

    created = client.post(
        "/receipts",
        json={
            "items": [
                {"name": "молоко", "price": 450},
            ]
        },
    )

    assert created.status_code == 201

    response = client.get(f"/receipts/{created.json()['id']}")

    assert response.status_code == 200

    data = response.json()

    assert data["calculated_total"] == "450.00"
    assert data["discrepancy"] is None


def test_create_category(client: TestClient):

    response = client.post(
        "/categories",
        json={"name": "тест"},
    )

    data = response.json()

    assert response.status_code == 201
    assert data["name"] == "тест"
    assert data["id"] > 0


def test_create_category_blank_name(client: TestClient):

    response = client.post(
        "/categories",
        json={"name": "   "},
    )

    assert response.status_code == 422
    assert len(response.json()["detail"]) == 1
    assert response.json()["detail"][0]["loc"] == ["body", "name"]


def test_create_category_duplicate(client: TestClient, make_category):
    make_category(name="тест")

    response = client.post(
        "/categories",
        json={"name": "тест"},
    )

    assert response.status_code == 409
    assert "detail" in response.json()


def test_create_receipt_with_category(client: TestClient, make_category, make_receipt):
    created_category = make_category(name="тест")

    created_receipt = make_receipt(
        items=[
            {
                "name": "молоко",
                "price": 100,
                "category_id": created_category["id"],
            }
        ]
    )

    response = client.get(f"/receipts/{created_receipt['id']}")

    assert response.status_code == 200

    data = response.json()

    assert len(data["items"]) == 1
    assert data["items"][0]["category_name"] == "тест"

    response_list = client.get("/receipts")

    assert response_list.status_code == 200

    data = response_list.json()

    assert len(data) == 1
    assert data[0]["id"] == created_receipt["id"]
    assert len(data[0]["items"]) == 1
    assert data[0]["items"][0]["category_name"] == "тест"


def test_create_receipt_without_category(client: TestClient, make_receipt):
    created_receipt = make_receipt()

    response = client.get(f"/receipts/{created_receipt['id']}")

    assert response.status_code == 200

    data = response.json()

    assert len(data["items"]) == 1
    assert data["items"][0]["category_name"] is None

    response_list = client.get("/receipts")

    assert response_list.status_code == 200

    data = response_list.json()

    assert len(data) == 1
    assert data[0]["id"] == created_receipt["id"]
    assert len(data[0]["items"]) == 1
    assert data[0]["items"][0]["category_name"] is None


def test_create_receipt_with_nonexistent_category(client: TestClient):

    response = client.post(
        "/receipts",
        json={
            "items": [
                {
                    "name": "молоко",
                    "price": 100,
                    "category_id": 999,
                }
            ]
        },
    )

    assert response.status_code == 400
    assert "detail" in response.json()


def test_create_receipt_mixed_existence_category(
    client: TestClient, make_category, make_receipt
):
    created_category = make_category(name="тест")

    created_receipt = make_receipt(
        items=[
            {
                "name": "молоко",
                "price": 100,
                "category_id": created_category["id"],
            },
            {
                "name": "хлеб",
                "price": 100,
            },
        ]
    )

    response = client.get(f"/receipts/{created_receipt['id']}")

    assert response.status_code == 200

    data = response.json()

    assert len(data["items"]) == 2
    assert data["items"][0]["category_name"] == "тест"
    assert data["items"][1]["category_name"] is None

    response_list = client.get("/receipts")

    assert response_list.status_code == 200

    data = response_list.json()

    assert len(data) == 1
    assert data[0]["id"] == created_receipt["id"]
    assert len(data[0]["items"]) == 2
    assert data[0]["items"][0]["category_name"] == "тест"
    assert data[0]["items"][1]["category_name"] is None


def test_parse_receipt(client: TestClient, monkeypatch):

    async def fake_parse(text: str, categories: dict[str, int]) -> ReceiptIn:
        return ReceiptIn(
            shop="Магнум",
            total=Decimal(650),
            items=[
                ItemIn(
                    name="молоко",
                    price=Decimal(450),
                )
            ],
        )

    monkeypatch.setattr(api.llm_client, "parse_receipt_text", fake_parse)

    response = client.post(
        "/receipts/parse",
        json={"text": "Магнум молоко 450 итог 650"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["shop"] == "Магнум"
    assert data["total"] == "650"
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "молоко"
    assert data["items"][0]["price"] == "450"


def test_parse_receipt_parse_error(client: TestClient, monkeypatch):

    async def fake_parse_error_parse(
        text: str, categories: dict[str, int]
    ) -> ReceiptIn:
        raise ReceiptParseError("тест")

    monkeypatch.setattr(api.llm_client, "parse_receipt_text", fake_parse_error_parse)

    response = client.post(
        "/receipts/parse",
        json={"text": "тестовый запрос"},
    )

    assert response.status_code == 422
    assert "detail" in response.json()
    assert response.json()["detail"] == "не удалось разобрать текст как чек"


def test_parse_receipt_service_error(client: TestClient, monkeypatch):

    async def fake_parse_error_service(
        text: str, categories: dict[str, int]
    ) -> ReceiptIn:
        raise LLMServiceError("тест")

    monkeypatch.setattr(api.llm_client, "parse_receipt_text", fake_parse_error_service)

    response = client.post(
        "/receipts/parse",
        json={"text": "тестовый запрос"},
    )

    assert response.status_code == 503

    assert "detail" in response.json()


def test_parse_receipt_string_too_short_error(client: TestClient):

    response = client.post("/receipts/parse", json={"text": "abc"})

    assert response.status_code == 422

    data = response.json()

    assert "detail" in data
    assert len(data["detail"]) == 1
    assert data["detail"][0]["type"] == "string_too_short"


def test_parse_receipt_passes_categories(
    client: TestClient, monkeypatch, make_category
):
    created = make_category(name="еда")
    received = {}

    async def fake(text: str, categories: dict[str, int]) -> ReceiptIn:
        received["categories"] = categories
        return ReceiptIn(
            shop="магнум",
            items=[
                ItemIn(
                    name="молоко",
                    price=Decimal(100),
                    category_id=created["id"],
                )
            ],
        )

    monkeypatch.setattr(api.llm_client, "parse_receipt_text", fake)

    client.post("/receipts/parse", json={"text": "магнум молоко 100"})

    assert received["categories"] == {"еда": created["id"]}


def test_get_stats(client: TestClient, make_category, make_receipt):
    first_category_id = make_category(name="первая")["id"]
    second_category_id = make_category(name="вторая")["id"]

    make_receipt(
        shop="тест",
        total=100,
        items=[
            {"name": "тест", "price": 333, "category_id": first_category_id},
            {"name": "тест", "price": 333, "category_id": first_category_id},
            {"name": "тест", "price": 333, "category_id": first_category_id},
            {"name": "тест", "price": 1000, "category_id": second_category_id},
            {"name": "тест", "price": 1000, "category_id": second_category_id},
            {"name": "тест", "price": 50},
            {"name": "тест", "price": 50},
        ],
    )

    response = client.get("/receipts/stats")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 3
    assert data[0]["category_name"] == "вторая"
    assert data[1]["category_name"] == "первая"
    assert data[2]["category_name"] is None

    assert data[0]["total_expenses"] == "2000.00"
    assert data[1]["total_expenses"] == "999.00"
    assert data[2]["total_expenses"] == "100.00"

    assert data[0]["items_count"] == 2
    assert data[1]["items_count"] == 3
    assert data[2]["items_count"] == 2


def test_get_stats_by_period(client: TestClient, make_category, make_receipt):
    created_category_id = make_category(name="тест")["id"]

    make_receipt(
        shop="тест",
        total=100,
        items=[
            {"name": "тест", "price": 333, "category_id": created_category_id},
        ],
        purchased_at=datetime(2026, 9, 25, tzinfo=UTC).isoformat(),
    )

    response_not_include = client.get(
        "/receipts/stats",
        params={
            "period_start": datetime(2026, 9, 24, tzinfo=UTC).isoformat(),
            "period_end": datetime(2026, 9, 25, tzinfo=UTC).isoformat(),
        },
    )

    assert response_not_include.status_code == 200

    data = response_not_include.json()

    assert len(data) == 0
    assert not data

    response_include = client.get(
        "/receipts/stats",
        params={
            "period_start": datetime(2026, 9, 24, tzinfo=UTC).isoformat(),
            "period_end": datetime(2026, 9, 25, 23, tzinfo=UTC).isoformat(),
        },
    )

    assert response_include.status_code == 200

    data = response_include.json()

    assert len(data) == 1

    assert data[0]["category_name"] == "тест"
    assert data[0]["total_expenses"] == "333.00"
    assert data[0]["items_count"] == 1


def test_get_stats_wrong_period(client: TestClient):
    response = client.get(
        "/receipts/stats",
        params={
            "period_start": datetime.now(UTC).isoformat(),
            "period_end": (datetime.now(UTC) - timedelta(1)).isoformat(),
        },
    )

    assert response.status_code == 422

    assert "detail" in response.json()
    assert response.json()["detail"] == "указан неверный период"


def test_get_stats_period_without_timezone(client: TestClient):
    response = client.get(
        "/receipts/stats",
        params={
            "period_start": datetime.now().isoformat(),
            "period_end": (datetime.now() - timedelta(1)).isoformat(),
        },
    )

    assert response.status_code == 422

    data = response.json()

    assert "detail" in data
    assert len(data["detail"]) == 2
    assert data["detail"][0]["loc"] == ["query", "period_start"]
    assert data["detail"][1]["loc"] == ["query", "period_end"]
    assert data["detail"][0]["type"] == "timezone_aware"
    assert data["detail"][1]["type"] == "timezone_aware"


def test_get_stats_one_bound(client: TestClient, make_receipt):

    make_receipt(purchased_at=datetime(2026, 5, 1, tzinfo=UTC).isoformat())
    make_receipt(purchased_at=datetime(2026, 9, 1, tzinfo=UTC).isoformat())

    response_assert_one = client.get(
        "/receipts/stats",
        params={"period_start": datetime(2026, 8, 31, tzinfo=UTC).isoformat()},
    )

    assert response_assert_one.status_code == 200
    assert response_assert_one.json()[0]["items_count"] == 1

    response_assert_two = client.get(
        "/receipts/stats",
        params={"period_start": datetime(2026, 4, 30, tzinfo=UTC).isoformat()},
    )

    assert response_assert_two.status_code == 200
    assert response_assert_two.json()[0]["items_count"] == 2

    response_assert_one = client.get(
        "/receipts/stats",
        params={"period_end": datetime(2026, 8, 1, tzinfo=UTC).isoformat()},
    )

    assert response_assert_one.status_code == 200
    assert response_assert_one.json()[0]["items_count"] == 1

    response_assert_two = client.get(
        "/receipts/stats",
        params={"period_end": datetime(2026, 10, 1, tzinfo=UTC).isoformat()},
    )

    assert response_assert_two.status_code == 200
    assert response_assert_two.json()[0]["items_count"] == 2


@pytest.mark.no_auth
def test_register(client: TestClient):
    response = client.post(
        "/auth/register",
        json={
            "email": "email@email.com",
            "password": "Abcdefg123",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["email"] == "email@email.com"
    assert "id" in data
    assert "password_hash" not in data


@pytest.mark.no_auth
def test_register_upper_email(client: TestClient):
    response = client.post(
        "/auth/register",
        json={
            "email": "TEST@MAIL.COM",
            "password": "testpass",
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] == "test@mail.com"


@pytest.mark.no_auth
@pytest.mark.parametrize(
    "email, status_code",
    [
        pytest.param(
            ("a" * 91) + "@mail.com",
            201,
            id="max_len",
        ),
        pytest.param(
            ("a" * 92) + "@mail.com",
            422,
            id="out_of_max_len",
        ),
    ],
)
def test_mail_credentials_constraints(client: TestClient, email, status_code):
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "testpass",
        },
    )

    assert response.status_code == status_code

    if status_code == 422:
        data = response.json()
        assert len(data["detail"]) == 1
        assert data["detail"][0]["loc"] == ["body", "email"]
        assert data["detail"][0]["type"] == "too_long"


@pytest.mark.no_auth
@pytest.mark.parametrize(
    "password, status_code",
    [
        pytest.param(
            "12345678",
            201,
            id="min_len",
        ),
        pytest.param(
            "1234567",
            422,
            id="out_of_min_len",
        ),
        pytest.param(
            f"{'1' * 128}",
            201,
            id="max_len",
        ),
        pytest.param(
            f"{'1' * 129}",
            422,
            id="out_of_max_len",
        ),
    ],
)
def test_password_credentials_constraints(client: TestClient, password, status_code):
    response = client.post(
        "/auth/register",
        json={
            "email": "test@mail.com",
            "password": password,
        },
    )

    assert response.status_code == status_code
    if status_code == 422:
        assert response.json()["detail"][0]["loc"] == ["body", "password"]


@pytest.mark.no_auth
def test_login(client: TestClient):
    response_register = client.post(
        "/auth/register",
        json={
            "email": "test@mail.com",
            "password": "testpass",
        },
    )

    assert response_register.status_code == 201

    response_login = client.post(
        "/auth/login",
        json={
            "email": "test@mail.com",
            "password": "testpass",
        },
    )

    assert response_login.status_code == 200

    data_login = response_login.json()

    assert "access_token" in data_login
    assert data_login["token_type"] == "bearer"

    authorization = {"Authorization": f"Bearer {data_login['access_token']}"}

    response_me = client.get("/me", headers=authorization)

    assert response_me.status_code == 200

    data_me = response_me.json()
    data_register = response_register.json()

    assert data_me["id"] == data_register["id"]
    assert data_me["email"] == data_register["email"]
    assert "password_hash" not in data_login
    assert "password_hash" not in data_me


@pytest.mark.no_auth
def test_login_short_password(client: TestClient):
    assert (
        client.post(
            "/auth/register",
            json={
                "email": "test@mail.com",
                "password": "testpass",
            },
        ).status_code
        == 201
    )

    response = client.post(
        "/auth/login",
        json={
            "email": "test@mail.com",
            "password": "short",
        },
    )

    assert response.status_code == 401
    assert "detail" in response.json()


@pytest.mark.no_auth
def test_create_receipt_with_nonexistent_user(client: TestClient):
    token = create_access_token(999, 15)

    response = client.post(
        "/receipts",
        json={"items": [{"name": "test", "price": 100}]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert "detail" in response.json()


@pytest.mark.no_auth
@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            {
                "email": "test@mail.com",
                "password": "Abcdefg123",
            },
            id="same_mail",
        ),
        pytest.param(
            {
                "email": "TEST@mail.com",
                "password": "Abcdefg123",
            },
            id="same_mail_upper_and_lower",
        ),
    ],
)
def test_register_same_mail(client: TestClient, payload, create_user):
    create_user(email="test@mail.com")

    response = client.post("/auth/register", json=payload)

    assert response.status_code == 409
    assert "detail" in response.json()


@pytest.mark.no_auth
@pytest.mark.parametrize(
    "bad_payload",
    [
        pytest.param(
            {
                "email": "test@mail.com",
                "password": "bad_testpass",
            },
            id="wrong_password",
        ),
        pytest.param(
            {
                "email": "nonexist@mail.com",
                "password": "testpass",
            },
            id="nonexistent_mail",
        ),
    ],
)
def test_login_bad_data(client: TestClient, bad_payload, create_user):
    create_user(
        email="test@mail.com",
        password="testpass",
    )

    response = client.post("/auth/login", json=bad_payload)

    assert response.status_code == 401

    data = response.json()

    assert len(data) == 1
    assert "detail" in data


@pytest.mark.no_auth
@pytest.mark.parametrize(
    "method, path, body",
    [
        pytest.param("GET", "/receipts", None, id="list_receipts"),
        pytest.param("GET", "/receipts/1", None, id="get_receipt"),
        pytest.param("GET", "/receipts/stats", None, id="get_stats"),
        pytest.param(
            "POST",
            "/receipts",
            {"items": [{"name": "test", "price": 100}]},
            id="create_receipt",
        ),
        pytest.param(
            "POST", "/receipts/parse", {"text": "test 100 test 50"}, id="get_parse"
        ),
        pytest.param("POST", "/categories", {"name": "test"}, id="create_category"),
    ],
)
def test_no_token(client: TestClient, method, path, body):
    response = client.request(method=method, url=path, json=body)

    assert response.status_code == 401


@pytest.mark.no_auth
@pytest.mark.parametrize(
    "token",
    [
        pytest.param("abc", id="not_token"),
        pytest.param(replaced, id="replaced_character"),
        pytest.param(
            jwt.encode({"sub": "1"}, "wrong_secret", algorithm="HS256"),
            id="wrong_secret",
        ),
        pytest.param(
            jwt.encode({"exp": 9999999999}, SECRET_KEY, algorithm="HS256"), id="no_sub"
        ),
        pytest.param(
            jwt.encode({"sub": "abc"}, SECRET_KEY, algorithm="HS256"), id="bad_sub"
        ),
    ],
)
def test_me_bad_token(client: TestClient, token):
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert "detail" in response.json()


@pytest.mark.no_auth
@pytest.mark.parametrize(
    "headers",
    [
        pytest.param(None, id="no_headers"),
        pytest.param({"Authorization": ""}, id="no_token"),
        pytest.param({"Authorization": "Basic abc"}, id="bad_authorization"),
    ],
)
def test_me_bad_headers(client: TestClient, headers):
    response = client.get("/me", headers=headers)

    assert response.status_code == 401
    assert "detail" in response.json()


@pytest.mark.no_auth
def test_me_expired_token(client: TestClient):
    token = create_access_token(user_id=1, duration_min=-1)

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert "detail" in response.json()


@pytest.mark.no_auth
def test_user_scope_foreign_receipt(client: TestClient, create_user):

    user_a_auth = create_user(email="user_A@mail.com", password="testpass")

    response_receipt_a = client.post(
        "/receipts",
        json={"shop": "shop_A", "items": [{"name": "товар", "price": 100}]},
        headers=user_a_auth,
    )

    assert response_receipt_a.status_code == 201

    user_b_auth = create_user(email="user_B@mail.com", password="testpass")

    response_get_receipt_by_id_a_auth = client.get(
        f"/receipts/{response_receipt_a.json()['id']}", headers=user_a_auth
    )

    assert response_get_receipt_by_id_a_auth.status_code == 200

    response_get_receipt_by_id_b_auth = client.get(
        f"/receipts/{response_receipt_a.json()['id']}", headers=user_b_auth
    )

    assert response_get_receipt_by_id_b_auth.status_code == 404
    assert "detail" in response_get_receipt_by_id_b_auth.json()
    assert len(response_get_receipt_by_id_b_auth.json()) == 1

    response_get_list_receipts_a_auth = client.get(
        "/receipts",
        headers=user_a_auth,
    )

    assert response_get_list_receipts_a_auth.status_code == 200

    assert len(response_get_list_receipts_a_auth.json()) == 1
    assert response_get_list_receipts_a_auth.json()[0]["shop"] == "shop_A"

    response_get_list_receipts_b_auth = client.get(
        "/receipts",
        headers=user_b_auth,
    )

    assert response_get_list_receipts_b_auth.status_code == 200
    assert len(response_get_list_receipts_b_auth.json()) == 0

    response_get_stats_a_auth = client.get(
        "/receipts/stats",
        headers=user_a_auth,
    )

    assert response_get_stats_a_auth.status_code == 200
    assert len(response_get_stats_a_auth.json()) == 1

    response_get_stats_b_auth = client.get(
        "/receipts/stats",
        headers=user_b_auth,
    )

    assert response_get_stats_b_auth.status_code == 200
    assert len(response_get_stats_b_auth.json()) == 0
