import pytest
from fastapi.testclient import TestClient


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
