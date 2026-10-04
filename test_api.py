from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from llm import LLMServiceError, ReceiptParseError
from models import ItemIn, ReceiptIn


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

    monkeypatch.setattr("api.parse_receipt_text", fake_parse)

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

    monkeypatch.setattr("api.parse_receipt_text", fake_parse_error_parse)

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

    monkeypatch.setattr("api.parse_receipt_text", fake_parse_error_service)

    response = client.post(
        "/receipts/parse",
        json={"text": "тестовый запрос"},
    )

    assert response.status_code == 503

    assert "detail" in response.json()
    assert response.json()["detail"] == "сервис модели недоступен или вернул ошибку"


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

    monkeypatch.setattr("api.parse_receipt_text", fake)

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
        purchased_at=datetime(2026, 9, 25, tzinfo=timezone.utc).isoformat(),
    )

    response_not_include = client.get(
        "/receipts/stats",
        params={
            "period_start": datetime(2026, 9, 24, tzinfo=timezone.utc).isoformat(),
            "period_end": datetime(2026, 9, 25, tzinfo=timezone.utc).isoformat(),
        },
    )

    assert response_not_include.status_code == 200

    data = response_not_include.json()

    assert len(data) == 0
    assert not data

    response_include = client.get(
        "/receipts/stats",
        params={
            "period_start": datetime(2026, 9, 24, tzinfo=timezone.utc).isoformat(),
            "period_end": datetime(2026, 9, 25, 23, tzinfo=timezone.utc).isoformat(),
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
            "period_start": datetime.now(timezone.utc).isoformat(),
            "period_end": (datetime.now(timezone.utc) - timedelta(1)).isoformat(),
        },
    )

    assert response.status_code == 422

    assert "detail" in response.json()
    assert response.json()["detail"] == "указан неверный период"


def test_get_stats_period_without_timezone(client: TestClient):
    response = client.get(
        "/receipts/stats",
        params={
            "period_start": datetime.now().isoformat(),  # noqa: DTZ005
            "period_end": (datetime.now() - timedelta(1)).isoformat(),  # noqa: DTZ005
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

    make_receipt(purchased_at=datetime(2026, 5, 1, tzinfo=timezone.utc).isoformat())
    make_receipt(purchased_at=datetime(2026, 9, 1, tzinfo=timezone.utc).isoformat())

    response_assert_one = client.get(
        "/receipts/stats",
        params={"period_start": datetime(2026, 8, 31, tzinfo=timezone.utc).isoformat()},
    )

    assert response_assert_one.status_code == 200
    assert response_assert_one.json()[0]["items_count"] == 1

    response_assert_two = client.get(
        "/receipts/stats",
        params={"period_start": datetime(2026, 4, 30, tzinfo=timezone.utc).isoformat()},
    )

    assert response_assert_two.status_code == 200
    assert response_assert_two.json()[0]["items_count"] == 2

    response_assert_one = client.get(
        "/receipts/stats",
        params={"period_end": datetime(2026, 8, 1, tzinfo=timezone.utc).isoformat()},
    )

    assert response_assert_one.status_code == 200
    assert response_assert_one.json()[0]["items_count"] == 1

    response_assert_two = client.get(
        "/receipts/stats",
        params={"period_end": datetime(2026, 10, 1, tzinfo=timezone.utc).isoformat()},
    )

    assert response_assert_two.status_code == 200
    assert response_assert_two.json()[0]["items_count"] == 2
