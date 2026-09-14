import psycopg

def save_receipt(conn: psycopg.Connection, items: list[tuple[str, int]], total: int | None, shop: str | None) -> int:

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
            [('тестовое молоко', 500),('тестовый хлеб', 300)],
            800,
            'ТестМаркет',
        )
        print('создан чек ', new_id)

    conn.close()

