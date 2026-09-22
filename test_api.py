from fastapi.testclient import TestClient


def test_ping(client):
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_receipt(client: TestClient, make_receipt):

    response = make_receipt(
        items=[
            {"name": "молоко", "price": 100},
            {"name": "хлеб", "price": 100},
        ],
    )

    response_get = client.get(f"/receipts/{response['id']}")

    assert response_get.status_code == 200

    data = response_get.json()

    assert data["shop"] == "Тест"
    assert data["total"] == "100.00"
    assert [(item["name"], item["price"]) for item in data["items"]] == [
        ("молоко", "100.00"),
        ("хлеб", "100.00"),
    ]


def test_get_receipt_not_found(client):
    response = client.get("/receipts/999")

    assert response.status_code == 404
    assert "detail" in response.json()


def test_receipts_list(client, make_receipt):
    make_receipt(shop="первый")
    make_receipt(shop="второй")

    response = client.get("/receipts")

    assert response.status_code == 200

    shops = [receipt["shop"] for receipt in response.json()]

    assert shops == ["второй", "первый"]


def test_pagination(client, make_receipt):

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


def test_create_receipt_empty_items(client):
    response = client.post(
        "/receipts",
        json={
            "shop": "test",
            "total": 100,
            "items": [],
        },
    )

    assert response.status_code == 422


def test_receipt_total_not_number(client):

    response = client.post(
        "/receipts",
        json={
            "shop": "test",
            "total": "дорого",
            "items": [{"name": "name", "price": 100}],
        },
    )

    assert response.status_code == 422


def test_create_receipt(client):
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


def test_extra_field(client):

    response = client.post(
        "/receipts",
        json={
            "shop": "Тест",
            "items": [
                {"name": "молоко", "price": 450, "лишнее": 1},
            ],
        },
    )

    assert response.status_code == 422


def test_empty_name(client):

    response = client.post(
        "/receipts",
        json={
            "items": [{"name": "   ", "price": 100}],
        },
    )

    assert response.status_code == 422


def test_negative_total(client):

    response = client.post(
        "/receipts",
        json={
            "total": -5000,
            "items": [{"name": "name", "price": 100}],
        },
    )

    assert response.status_code == 422
