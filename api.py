from db import save_receipt, fetch_receipt, fetch_receipts
from models import ReceiptIn, ReceiptOut, CategoryOut
from fastapi import FastAPI, HTTPException, Query
from psycopg_pool import ConnectionPool
import os

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
        response_id = save_receipt(conn=conn, items=items, total=receipt.total, shop=receipt.shop)
        created_receipt = fetch_receipt(conn=conn, receipt_id=response_id)

    if created_receipt is None:
        raise RuntimeError("чек не найден сразу после создания")

    return created_receipt

@app.get("/receipts")
def get_list_receipts(
        limit: int = Query(default=20, ge=1, le=100), 
        offset: int = Query(default=0, ge=0) 
    ) -> list[ReceiptOut]:

    with pool.connection() as conn:
        result_list = fetch_receipts(conn=conn, limit=limit, offset=offset)

    return result_list

@app.get("/receipts/{receipt_id}", responses={404: {"description": "Чек не найден"}})
def get_receipt(receipt_id: int) -> ReceiptOut:
    with pool.connection() as conn:
        result_receipt_obj = fetch_receipt(conn=conn, receipt_id=receipt_id)

    if result_receipt_obj is None:
        raise HTTPException(status_code=404, detail="чек не найден")
    
    return result_receipt_obj

@app.get("/ping")
def ping() -> dict[str, str]:
    return {"status":"ok"}

@app.get("/categories")
def categories() -> list[CategoryOut]:
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute("select id, name from categories")
        rows = cur.fetchall()

    result = [CategoryOut(id=cat_id, name=name) for cat_id, name in rows]
    return result
