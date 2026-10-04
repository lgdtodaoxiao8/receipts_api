from collections import defaultdict
from datetime import datetime
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row

from models import CategoryOut, ItemOut, ReceiptOut, Stat


def save_receipt(
    conn: psycopg.Connection,
    items: list[tuple[str, Decimal, int | None]],
    total: Decimal | None,
    shop: str | None,
    purchased_at: datetime | None,
) -> int:

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO receipts (purchased_at, total, shop)
            VALUES (COALESCE(%s, now()), %s, %s)
            RETURNING id
            """,
            (purchased_at, total, shop),
        )

        fetched_row = cur.fetchone()

        if fetched_row is None:
            raise RuntimeError("INSERT не вернул id")

        receipt_id = fetched_row[0]

        items_values_list = [
            (name, price, receipt_id, category_id) for name, price, category_id in items
        ]

        cur.executemany(
            """
            INSERT INTO items (name, price, receipt_id, category_id) 
            VALUES (%s, %s, %s, %s)
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
            SELECT i.name, i.price, c.name AS category_name
            FROM items i
            LEFT JOIN categories c ON i.category_id = c.id
            WHERE i.receipt_id = %s 
            ORDER BY i.id
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
            SELECT i.receipt_id, i.name, i.price, c.name AS category_name
            FROM items i
            LEFT JOIN categories c ON i.category_id = c.id
            WHERE i.receipt_id = ANY(%s)
            ORDER BY i.receipt_id, i.id
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


def save_category(conn: psycopg.Connection, name: str) -> CategoryOut:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO categories (name)
            VALUES (%s)
            RETURNING id, name
            """,
            (name,),
        )

        created = cur.fetchone()

    if created is None:
        raise RuntimeError("INSERT не вернул строку")

    return CategoryOut(**created)


def fetch_categories(conn: psycopg.Connection) -> list[CategoryOut]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, name FROM categories ORDER BY id")
        categories_dicts = cur.fetchall()
    return [CategoryOut(**category_dict) for category_dict in categories_dicts]


def fetch_categories_stats(
    conn: psycopg.Connection,
    period_start: datetime | None,
    period_end: datetime | None,
) -> list[Stat]:

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT c.name AS category_name, sum(i.price) AS total_expenses, count(i.id) AS items_count
            FROM items i
            LEFT JOIN categories c on i.category_id = c.id
            JOIN receipts r on i.receipt_id = r.id
            WHERE (%s::timestamptz IS NULL OR r.purchased_at >= %s)
            AND (%s::timestamptz IS NULL OR r.purchased_at < %s)
            GROUP BY c.name
            ORDER BY sum(i.price) DESC, c.name
        """,
            (period_start, period_start, period_end, period_end),
        )
        response = cur.fetchall()

    list_stats = [Stat(**stat) for stat in response]

    return list_stats
