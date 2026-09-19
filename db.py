from models import ReceiptOut, ItemOut
from collections import defaultdict
from psycopg.rows import dict_row
from decimal import Decimal
import psycopg

def save_receipt(conn: psycopg.Connection, items: list[tuple[str, Decimal]], total: Decimal | None, shop: str | None) -> int:

    with conn.cursor() as cur:
        cur.execute(
            """
            insert into receipts (purchased_at, total, shop)
            values (now(), %s, %s)
            returning id
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
            insert into items (name, price, receipt_id) 
            values (%s, %s, %s)
            """,
            items_values_list
        )

    return receipt_id 

def fetch_receipt(conn: psycopg.Connection, receipt_id: int) -> ReceiptOut | None:
    with conn.cursor(row_factory=dict_row) as cur:

        cur.execute(
            """
            select id, purchased_at, total, shop
            from receipts
            where id = %s
            """,
            (receipt_id,)
        )

        receipt_row = cur.fetchone()

        if receipt_row is None:
            return None

        cur.execute(
            """
            select name, price 
            from items 
            where receipt_id = %s 
            order by id
            """, 
            (receipt_id,)
        )

        items_rows = cur.fetchall()

    items = [ItemOut(**item_row) for item_row in items_rows]

    return ReceiptOut(**receipt_row, items=items)


def fetch_receipts(conn: psycopg.Connection, limit: int, offset: int) -> list[ReceiptOut]:

    with conn.cursor(row_factory=dict_row) as cur:

        cur.execute(
            """
            select id, shop, total, purchased_at
            from receipts
            order by purchased_at desc, id desc
            limit %s offset %s
            """,
            (limit, offset)
        )

        receipts_dicts = cur.fetchall()

        if not receipts_dicts:
            return []

        receipts_ids = [receipt_dict["id"] for receipt_dict in receipts_dicts]

        cur.execute(
            """
            select receipt_id, name, price
            from items
            where receipt_id = any(%s)
            order by receipt_id, id
            """,
            (receipts_ids,)
        )

        items_dicts = cur.fetchall()

        items_by_receipt: dict[int, list[ItemOut]] = defaultdict(list)

        for item_dict in items_dicts:
            items_by_receipt[item_dict["receipt_id"]].append(
                ItemOut(name=item_dict["name"], price=item_dict["price"])
            )

        receipts_list: list[ReceiptOut] = []

        for receipt_dict in receipts_dicts:
            receipts_list.append(
                ReceiptOut(
                    id=receipt_dict["id"],
                    shop=receipt_dict["shop"],
                    total=receipt_dict["total"],
                    purchased_at=receipt_dict["purchased_at"],
                    items=items_by_receipt.get(receipt_dict["id"], [])
                )
            )

    return receipts_list
        


if __name__ == "__main__":
    conn = psycopg.connect(
        host="localhost",
        port=5432,
        dbname="receipts",
        user="postgres",
        password="secret",
    )

    with conn:
        new_id = save_receipt(
            conn, 
            [('тестовое молоко', Decimal(500)),('тестовый хлеб', Decimal(300))],
            Decimal(800),
            'ТестМаркет',
        )
        print('создан чек ', new_id)

    conn.close()

