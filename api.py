import os

import psycopg
from fastapi import FastAPI, HTTPException, Query
from psycopg_pool import ConnectionPool

from db import (
    fetch_categories,
    fetch_receipt,
    fetch_receipts,
    save_category,
    save_receipt,
)
from models import CategoryIn, CategoryOut, ReceiptIn, ReceiptOut

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:secret@localhost:5432/receipts",
)

pool = ConnectionPool(DATABASE_URL, open=True)

app = FastAPI()


@app.post("/receipts", status_code=201)
def create_receipt(receipt: ReceiptIn) -> ReceiptOut:
    items = [(item.name, item.price) for item in receipt.items]

    with pool.connection() as conn:
        receipt_id = save_receipt(
            conn=conn, items=items, total=receipt.total, shop=receipt.shop
        )
        created_receipt = fetch_receipt(conn=conn, receipt_id=receipt_id)

    if created_receipt is None:
        raise RuntimeError("чек не найден сразу после создания")

    return created_receipt


@app.get("/receipts")
def list_receipts(
    limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0)
) -> list[ReceiptOut]:

    with pool.connection() as conn:
        result_list = fetch_receipts(conn=conn, limit=limit, offset=offset)

    return result_list


@app.get("/receipts/{receipt_id}", responses={404: {"description": "Чек не найден"}})
def get_receipt(receipt_id: int) -> ReceiptOut:
    with pool.connection() as conn:
        receipt = fetch_receipt(conn=conn, receipt_id=receipt_id)

    if receipt is None:
        raise HTTPException(status_code=404, detail="чек не найден")

    return receipt


@app.get("/ping")
def ping() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/categories",
    status_code=201,
    responses={409: {"description": "категория уже существует"}},
)
def create_category(category: CategoryIn) -> CategoryOut:
    with pool.connection() as conn:
        try:
            return save_category(conn=conn, name=category.name)
        except psycopg.errors.UniqueViolation:
            raise HTTPException(status_code=409, detail="категория уже существует")


@app.get("/categories")
def categories() -> list[CategoryOut]:
    with pool.connection() as conn:
        result = fetch_categories(conn=conn)

    return result
