[![CI](https://github.com/lgdtodaoxiao8/receipts_api/actions/workflows/ci.yml/badge.svg)](https://github.com/lgdtodaoxiao8/receipts_api/actions/workflows/ci.yml)

[Русская версия](README.ru.md)

# Receipts API

A purchase tracking service. It accepts a receipt containing a list of items, saves the data to PostgreSQL, allows items to be linked to spending categories, and calculates the discrepancy between the sum of the individual items and the total amount stated on the receipt.

It addresses the challenge of manual expense tracking: instead of entering purchases into a spreadsheet, you can send them to the API for subsequent analysis.

## Stack

Python 3.12, FastAPI, PostgreSQL, Redis, psycopg 3, Pydantic, Alembic, Docker, pytest.

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

`docker compose` brings up two databases, the main one on port 5432 and the test one on 5433, plus Redis on 6379. Alembic creates the tables in the databases, and the addresses of the database and Redis are read from the `.env` file. Parsing receipts from text requires an OpenAI key, which is also read from `.env`. The rest of the endpoints work without it. A template sits in `.env.example`; copy it and adjust the values if you need to.

Post-launch API documentation: http://127.0.0.1:8000/docs

## Tests

```bash
pip install -r requirements-dev.txt
DATABASE_URL="postgresql://postgres:secret@localhost:5433/receipts_test" alembic upgrade head
pytest
```

The test database address is passed explicitly because `.env` holds the main one, while the schema has to be applied to both. The tests themselves take the address from `pytest.ini` and never reach the main database.

The tests cover success scenarios, input validation, error codes, pagination, working with categories, and discrepancy calculation. Before every test the tables are cleared, and so is the cache: it lives in a separate Redis database, so the working one is left alone. Neither the execution order nor repeated runs affect the result.

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | /receipts/parse | Parse receipt text into a structure |
| POST | /receipts | Create a receipt |
| GET | /receipts | List of receipts with pagination |
| GET | /receipts/stats | Spending summary by category over a period |
| GET | /receipts/{id} | Receipt by ID |
| POST | /categories | Create a category |
| GET | /categories | List of categories |
| GET | /ping | Health check |

Response codes: 422 if the data fails validation, the text cannot be parsed as a receipt, or the period bounds come without a time zone or end before they start; 404 for a receipt that does not exist; 409 when creating a category whose name is already taken; 400 if an item refers to a category that is not there; and 503 if the model service is unavailable.

## Examples

Parsing text. The service sends the text to a language model along with the list of existing categories and returns a structure without saving anything: the client checks the result first and then submits it through the regular `POST /receipts`. The model picks a category only from the list it was given, and sets null when none of them fit.

```json
POST /receipts/parse

{
  "text": "magnum\nmilk 450\nbread 200\ntotal 650"
}
```

```json
200 OK

{
  "shop": "magnum",
  "total": "650",
  "items": [
    {"name": "milk", "price": "450", "category_id": 1},
    {"name": "bread", "price": "200", "category_id": 2}
  ]
}
```

If the text does not look like a receipt, the response is 422. If the model service did not answer, it is 503.

Creating a receipt. The `category_id` field on an item is optional: you can set it or leave it out. A default set of categories is inserted by a migration on first run, and your own are added through `POST /categories`.
The time of purchase can be passed in the `purchased_at` field, with a time zone required. Leave it out and the time the record was created is used instead, so for receipts from earlier days it is better to state it.

```json
POST /receipts

{
  "shop": "Magnum",
  "total": 650,
  "purchased_at": "2026-09-26T19:12:03Z",
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
  "purchased_at": "2026-09-26T19:12:03Z",
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

Spending summary. Groups items by category over a period and sorts by amount. The bounds are optional; without them everything is counted over all time.

```
GET /receipts/stats?period_start=2026-09-01T00:00:00Z&period_end=2026-10-01T00:00:00Z
```

```json
200 OK

[
  {"category_name": "food", "total_expenses": "12400.00", "items_count": 23},
  {"category_name": "drinks", "total_expenses": "3200.00", "items_count": 8},
  {"category_name": null, "total_expenses": "750.00", "items_count": 3}
]
```

The start of the period is included, the end is not. That way neighbouring periods do not overlap and a receipt on the boundary is not counted in both. Items without a category come as their own row, with `category_name` set to `null`.

## Data schema

Three tables. `receipts` stores the receipt: purchase time, store, and stated total.
`items` stores the line items, referencing the receipt and, optionally, a category.
`categories` stores the list of expense categories.

Line items are read through a `LEFT JOIN` with the categories, so an item without a category does not disappear from the response; its `category_name` is simply empty.

The category list is populated by a migration during deployment: sixteen categories covering an ordinary supermarket receipt. They can be removed or extended through the API, and text parsing works with whatever is in the database at the time of the request.

## Technical solutions

**NUMERIC instead of float for money.** The `float` type stores numbers in a binary representation, and some decimal fractions cannot be represented exactly in this format. This leads to the classic `0.1 + 0.2 = 0.30000000000000004`. While this may seem insignificant, the discrepancy accumulates into a noticeable error when processing a stream of transactions. The `NUMERIC` type stores decimal numbers precisely.

**Two queries instead of a JOIN when reading a list.** The straightforward approach is to request a list of receipts and then, in a loop, query the line items for each one; for twenty receipts, this results in twenty-one database queries, the N+1 problem. Here, only two queries are made regardless of the number of receipts: first for the receipts, then for the line items of all those receipts at once using `ANY`, followed by grouping by `receipt_id` in Python. A single query with a `JOIN` isn't suitable either: receipt data would be duplicated in every row, and the nested structure would have to be assembled manually.

**TIMESTAMPTZ instead of TIMESTAMP.** It stores a point in time in UTC and returns it in the requester's time zone. A TIMESTAMP simply stores the numbers on the clock face without a time zone reference; consequently, two moments from different time zones become indistinguishable, and time-based sorting can break. For the same reason both the time of purchase and the period bounds in the summary are only accepted with an explicit time zone: without one the moment is undefined, and the database fills it in from the connection's setting, which would make the result depend on the server's configuration rather than on the data sent.

**Two-level validation.** Pydantic filters out invalid data at the API boundary and returns a 422 response to the client, specifying the exact field involved. Meanwhile, database CHECK constraints ensure that no garbage data enters the tables by any means, including direct writes via scripts or psql.

**Connection pool.** Establishing a connection to Postgres takes tens of milliseconds, while the query itself takes about a millisecond. This means almost the entire response time would be consumed by the connection process, and under load the database would not be able to handle the influx of new processes. A pool maintains ready-made connections: a query takes a free one, does its work, and returns it.

**Handling external service failures.** Calls to the language model can fail in various ways: timeouts, rate limit exceedances, server-side errors, or responses in unexpected formats. All these scenarios are mapped to two custom exceptions: one indicating a failure to parse the text, and the other indicating that the service is unavailable. For the client, these translate into 422 and 503 status codes, respectively, allowing them to identify the cause and determine whether to retry the request. The request itself is executed asynchronously, enabling the handler to process other requests while awaiting a response from the model service.

**Categories are picked from the existing reference list.** Letting the model name a category freely fills the list with synonyms such as food, groceries, nutrition and food products, which makes any statistics built on them meaningless. So the request carries the list of existing categories and the model picks only from those. An item that fits none of them is left without a category at all: a separate "other" entry would be indistinguishable from the case where detection simply failed.

**Caching the parse.** A call to the model costs money and takes a few seconds, while the same text always parses the same way. The result goes into Redis for a day, keyed by a hash of the text together with the list of categories: once the reference list changes, the old parse is no longer valid, it still holds the previous identifiers. The lifetime is there for a different reason: the prompt and the model change over time, and a record that lives forever would eventually serve a parse made by rules the code no longer has. None of this is required for the service to work: when Redis is unavailable, it simply goes to the model and answers more slowly.

**Index for time-based filtering.** The summary selects receipts based on `purchased_at`, and the list of receipts is sorted by the same column. Without an index, the database reads the entire table and checks every row in both cases; while this is imperceptible with a thousand receipts, it takes seconds with a million. An index keeps the column values sorted, allowing the required range to be located by traversing the tree, after which the data is read sequentially. The trade-off is disk space and slightly slower insertions, as every new receipt must be written to the index.

## On the agenda

Per-user data separation and authentication.

## License

MIT, see [LICENSE](LICENSE).