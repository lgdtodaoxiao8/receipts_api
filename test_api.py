from fastapi.testclient import TestClient
from api import app

client = TestClient(app)


def test_ping(clean_db):
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"status" : "ok"}

def test_create_receipt(clean_db):
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
    assert len(data["items"]) == 2
    assert data["id"] > 0