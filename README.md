[![CI](https://github.com/lgdtodaoxiao8/receipts_api/actions/workflows/ci.yml/badge.svg)](https://github.com/lgdtodaoxiao8/receipts_api/actions/workflows/ci.yml)

[Русская версия](README.ru.md)

# Receipts API

A purchase tracking service. It accepts a receipt containing a list of items, saves the data to PostgreSQL, allows items to be linked to spending categories, and calculates the discrepancy between the sum of the individual items and the total amount stated on the receipt.

It addresses the challenge of manual expense tracking: instead of entering purchases into a spreadsheet, you can send them to the API for subsequent analysis.

## Stack

Python 3.12, FastAPI, PostgreSQL, psycopg 3, Pydantic, Alembic, Docker, pytest.

## Launching

```bash
git clone https://github.com/lgdtodaoxiao8/receipts_api.git
cd receipts_api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d
alembic upgrade head
fastapi dev api.py
```

`docker compose` brings up two databases: the main one on port 5432 and the test one on 5433. Alembic creates the tables in both, and the database address is read from the `.env` file. A template sits in `.env.example`; copy it and adjust the values if you need to.

Post-launch API documentation: http://127.0.0.1:8000/docs

## Tests

```bash
pip install -r requirements-dev.txt
DATABASE_URL="postgresql://postgres:secret@localhost:5433/receipts_test" alembic upgrade head
pytest
```

The test database address is passed explicitly because `.env` holds the main one, while the schema has to be applied to both. The tests themselves take the address from `pytest.ini` and never reach the main database.

The tests cover success scenarios, input validation, error codes, pagination, working with categories, and discrepancy calculation. The tables are cleared before every test, so neither the execution order nor repeated runs affect the result.

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | /receipts | Create a receipt |
| GET | /receipts | List of receipts with pagination |
| GET | /receipts/{id} | Receipt by ID |
| POST | /categories | Create a category |
| GET | /categories | List of categories |
| GET | /ping | Health check |

Response codes: 422 if the data fails validation, 404 for a receipt that does not exist, 409 when creating a category whose name is already taken, and 400 if an item refers to a category that is not there.

## Examples

Creating a receipt. The `category_id` field on an item is optional: you can set it if the category you need has already been created through `POST /categories`, or you can leave it out entirely.

```json
POST /receipts

{
  "shop": "Magnum",
  "total": 650,
  "items": [
    {"name": "milk", "price": 450, "category_id": 1},
    {"name": "bread", "price": 200}
  ]
}
```

The response contains the saved receipt. The category name is substituted for its identifier, and two computed fields appear next to the stated total: `calculated_total`, the sum of the items, and `discrepancy`, the difference between that sum and the total. A positive value means the items together cost more than the receipt claims.

```json
201 Created

{
  "id": 1,
  "shop": "Magnum",
  "total": "650.00",
  "purchased_at": "2026-09-26T19:12:03.481220Z",
  "items": [
    {"name": "milk", "price": "450.00", "category_name": "food"},
    {"name": "bread", "price": "200.00", "category_name": null}
  ],
  "calculated_total": "650.00",
  "discrepancy": "0.00"
}
```

If the receipt has no stated total, `discrepancy` comes back as `null`: there is nothing to compare against.

The list of receipts is returned in pages; the size and the offset are set by the `limit` and `offset` parameters. The default is twenty receipts from the beginning, most recent first.

```
GET /receipts?limit=20&offset=0
```

## Data schema

Three tables. `receipts` stores the receipt: purchase time, store, and stated total.
`items` stores the line items, referencing the receipt and, optionally, a category.
`categories` stores the list of expense categories.

Line items are read through a `LEFT JOIN` with the categories, so an item without a category does not disappear from the response; its `category_name` is simply empty.

## Technical solutions

**NUMERIC instead of float for money.** The `float` type stores numbers in a binary representation, and some decimal fractions cannot be represented exactly in this format. This leads to the classic `0.1 + 0.2 = 0.30000000000000004`. While this may seem insignificant, the discrepancy accumulates into a noticeable error when processing a stream of transactions. The `NUMERIC` type stores decimal numbers precisely.

**Two queries instead of a JOIN when reading a list.** The straightforward approach is to request a list of receipts and then, in a loop, query the line items for each one; for twenty receipts, this results in twenty-one database queries, the N+1 problem. Here, only two queries are made regardless of the number of receipts: first for the receipts, then for the line items of all those receipts at once using `ANY`, followed by grouping by `receipt_id` in Python. A single query with a `JOIN` isn't suitable either: receipt data would be duplicated in every row, and the nested structure would have to be assembled manually.

**TIMESTAMPTZ instead of TIMESTAMP.** It stores a point in time in UTC and returns it in the requester's time zone. A TIMESTAMP simply stores the numbers on the clock face without a time zone reference; consequently, two moments from different time zones become indistinguishable, and time-based sorting can break.

**Two-level validation.** Pydantic filters out invalid data at the API boundary and returns a 422 response to the client, specifying the exact field involved. Meanwhile, database CHECK constraints ensure that no garbage data enters the tables by any means, including direct writes via scripts or psql.

**Connection pool.** Establishing a connection to Postgres takes tens of milliseconds, while the query itself takes about a millisecond. This means almost the entire response time would be consumed by the connection process, and under load the database would not be able to handle the influx of new processes. A pool maintains ready-made connections: a query takes a free one, does its work, and returns it.

## On the agenda

Parsing receipt text using a language model, automatic category detection, and caching in Redis.

## License

MIT, see [LICENSE](LICENSE).