import os
import psycopg
import pytest

DATABASE_URL = os.environ["DATABASE_URL"]

@pytest.fixture
def clean_db():
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE items, receipts, categories RESTART IDENTITY CASCADE")
    yield