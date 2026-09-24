from collections import defaultdict
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row

from models import CategoryOut, ItemOut, ReceiptOut


def save_receipt(
    conn: psycopg.Connection,
    items: list[tuple[str, Decimal]],
    total: Decimal | None,
    shop: str | None,
) -> int:

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO receipts (purchased_at, total, shop)
            VALUES (now(), %s, %s)
            RETURNING id
            """,
            (total, shop),
        )

        fetched_row = cur.fetchone()

        if fetched_row is None:
            raise RuntimeError("INSERT не вернул id")

        receipt_id = fetched_row[0]

        items_values_list = [(name, price, receipt_id) for name, price in items]

        cur.executemany(
            """
            INSERT INTO items (name, price, receipt_id) 
            VALUES (%s, %s, %s)
            """,
            items_values_list,
        )

    return receipt_id


def fetch_receipt(conn: psycopg.Connection, receipt_id: int) -> ReceiptOut | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, purchased_at, total, shop
            FROM receipts
            WHERE id = %s
            """,
            (receipt_id,),
        )

        receipt_row = cur.fetchone()

        if receipt_row is None:
            return None

        cur.execute(
            """
            SELECT name, price 
            FROM items 
            WHERE receipt_id = %s 
            ORDER BY id
            """,
            (receipt_id,),
        )

        items_rows = cur.fetchall()

    items = [ItemOut(**item_row) for item_row in items_rows]

    return ReceiptOut(**receipt_row, items=items)


def fetch_receipts(
    conn: psycopg.Connection, limit: int, offset: int
) -> list[ReceiptOut]:

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, shop, total, purchased_at
            FROM receipts
            ORDER BY purchased_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )

        receipts_dicts = cur.fetchall()

        if not receipts_dicts:
            return []

        receipts_ids = [receipt_dict["id"] for receipt_dict in receipts_dicts]

        cur.execute(
            """
            SELECT receipt_id, name, price
            FROM items
            WHERE receipt_id = ANY(%s)
            ORDER BY receipt_id, id
            """,
            (receipts_ids,),
        )

        items_dicts = cur.fetchall()

    items_by_receipt: dict[int, list[ItemOut]] = defaultdict(list)

    for item_dict in items_dicts:
        receipt_id = item_dict.pop("receipt_id")
        items_by_receipt[receipt_id].append(ItemOut(**item_dict))

    result = [
        ReceiptOut(**receipt_dict, items=items_by_receipt.get(receipt_dict["id"], []))
        for receipt_dict in receipts_dicts
    ]

    return result


def fetch_categories(conn: psycopg.Connection) -> list[CategoryOut]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, name FROM categories ORDER BY id")
        categories_dicts = cur.fetchall()
    return [CategoryOut(**category_dict) for category_dict in categories_dicts]
