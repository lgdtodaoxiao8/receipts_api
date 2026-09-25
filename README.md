[Русская версия](README.ru.md)

# Receipts API

A purchase tracking service. It accepts a receipt containing a list of items, saves the data to PostgreSQL, allows items to be linked to spending categories, and calculates the discrepancy between the sum of the individual items and the total amount stated on the receipt.

It addresses the challenge of manual expense tracking: instead of entering purchases into a spreadsheet, you can send them to the API for subsequent analysis.

## Stack

Python 3.12, FastAPI, PostgreSQL, psycopg 3, Pydantic, Alembic, Docker, pytest.

## Launching

```bash
git clone <url>
cd receipts
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d
DATABASE_URL="postgresql://postgres:secret@localhost:5432/receipts" alembic upgrade head
fastapi dev api.py
```

Post-launch API documentation: http://127.0.0.1:8000/docs

## Tests

```bash
DATABASE_URL="postgresql://postgres:secret@localhost:5433/receipts_test" alembic upgrade head
pytest
```

32 tests: success scenarios, input validation, error codes, pagination, discrepancy calculation.

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | /receipts | Create a receipt |
| GET | /receipts | List of receipts with pagination |
| GET | /receipts/{id} | Receipt by ID |
| POST | /categories | Create a category |
| GET | /categories | List of categories |
| GET | /ping | Health check |

## Data schema

Three tables. `receipts` stores the receipt: purchase time, store, and stated total.
`items` stores the line items, referencing the receipt and—optionally—a category.
`categories` stores the list of expense categories.

## Technical solutions

**NUMERIC instead of float for money.** The `float` type stores numbers in a binary representation, and some decimal fractions cannot be represented exactly in this format. This leads to the classic `0.1 + 0.2 = 0.30000000000000004`. While this may seem insignificant, the discrepancy accumulates into a noticeable error when processing a stream of transactions. The `NUMERIC` type stores decimal numbers precisely.

**Two queries instead of a JOIN when reading a list.** The straightforward approach is to request a list of receipts and then, in a loop, query the line items for each one; for twenty receipts, this results in twenty-one database queries—the N+1 problem. Here, only two queries are made regardless of the number of receipts: first for the receipts, then for the line items of all those receipts at once using `ANY`, followed by grouping by `receipt_id` in Python. A single query with a `JOIN` isn't suitable either: receipt data would be duplicated in every row, and the nested structure would have to be assembled manually.

**TIMESTAMPTZ instead TIMESTAMP.** It stores a point in time in UTC and returns it in the requester's time zone. A TIMESTAMP simply stores the numbers on the clock face without a time zone reference; consequently, two moments from different time zones become indistinguishable, and time-based sorting can break.

**Two-level validation.** Pydantic filters out invalid data at the API boundary and returns a 422 response to the client, specifying the exact field involved. Meanwhile, database CHECK constraints ensure that no garbage data enters the tables by any means—including direct writes via scripts or psql.

**Connections pool.** Establishing a connection to Postgres takes tens of milliseconds, while the query itself takes about a millisecond. This means 95% of the time would be spent on establishing the connection. A connection pool maintains ready-made connections; a query takes an available one, performs its task, and returns it to the pool. Without a pool, almost the entire response time would be consumed by the connection process, and under load, the database would not be able to handle the influx of new processes.

## On the agenda

Parsing receipt text using a language model, automatic category detection, and caching in Redis.