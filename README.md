[![CI](https://github.com/lgdtodaoxiao8/receipts_api/actions/workflows/ci.yml/badge.svg)](https://github.com/lgdtodaoxiao8/receipts_api/actions/workflows/ci.yml)

[Русская версия](README.ru.md)

# Receipts API

A service for tracking purchases. It takes a receipt with a list of items and stores it in PostgreSQL. Items can be linked to spending categories, and the service checks whether the items add up to the total printed on the receipt. You don't have to type a receipt in by hand: a language model can turn its text into structured data.

Every user sees only their own receipts. You sign in with email and password, and after that requests carry a JWT.

The idea is simple: instead of a spreadsheet you fill in manually, receipts go to the API, and you get a spending summary by category out of them.

## Stack

Python 3.12, FastAPI, PostgreSQL, Redis, psycopg 3, Pydantic, Alembic, PyJWT, argon2, Docker, pytest.

## Running it

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

`docker compose` starts two databases, the main one on port 5432 and the test one on 5433, plus Redis on 6379. Alembic creates the tables. The app reads the database and Redis addresses from `.env`; there is a template in `.env.example`.

Before the first run, set `JWT_SECRET` in `.env`. It is the key that signs tokens. Don't leave it empty: anyone can forge a token signed with an empty key. You can generate one like this:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Parsing receipt text needs an OpenAI key in `OPENAI_API_KEY`. Everything else works without it.

API docs once it's running: http://127.0.0.1:8000/docs

## Authentication

Register first:

```json
POST /auth/register

{
  "email": "user@mail.com",
  "password": "my-password"
}
```

```json
201 Created

{"id": 1, "email": "user@mail.com"}
```

Then sign in with the same credentials:

```json
POST /auth/login

{
  "email": "user@mail.com",
  "password": "my-password"
}
```

```json
200 OK

{"access_token": "eyJhbGciOi...", "token_type": "bearer"}
```

From then on, send the token in a header with every request:

```
Authorization: Bearer eyJhbGciOi...
```

A token lasts 15 minutes; after that you sign in again. `GET /me` returns the id and email of the token's owner.

Emails are lowercased, so `User@Mail.com` and `user@mail.com` are the same account. An email can be up to 100 characters, a password from 8 to 128.

In Swagger, protected endpoints have an `authorization` field. Put the whole string there, including the word `Bearer`.

## API

| Method | Path | Description | Token required |
|--------|------|-------------|----------------|
| POST | /auth/register | Register | no |
| POST | /auth/login | Sign in, get a token | no |
| GET | /me | Current user | yes |
| POST | /receipts/parse | Parse receipt text into structured data | yes |
| POST | /receipts | Create a receipt | yes |
| GET | /receipts | Your receipts, paginated | yes |
| GET | /receipts/stats | Your spending by category over a period | yes |
| GET | /receipts/{id} | One of your receipts by id | yes |
| POST | /categories | Create a category | yes |
| GET | /categories | List categories | no |
| GET | /ping | Health check | no |

Response codes:

- 401: no token, a broken or expired token, wrong email or password at sign-in, or the token's user no longer exists;
- 404: the receipt doesn't exist or belongs to someone else;
- 409: the email is already registered, or a category with that name already exists;
- 400: an item refers to a category that doesn't exist;
- 422: the data failed validation, the text couldn't be parsed as a receipt, or the period bounds have no time zone or the end comes before the start;
- 503: the model service is unavailable.

## Examples

All requests below are sent with the `Authorization` header.

Parsing text. The service sends the text to a language model together with the list of existing categories and returns structured data. It doesn't save anything: the client looks at the result first and then sends it through the regular `POST /receipts`. The model only picks categories from the list it was given and uses null when none fit.

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

If the text doesn't look like a receipt, you get 422. If the model service didn't answer, 503.

Creating a receipt. `category_id` on an item is optional. A default set of categories is added by a migration on first run, and you can add your own through `POST /categories`. The purchase time goes in `purchased_at` and must include a time zone. If you leave it out, the time the record was created is used, so for receipts from earlier days it's better to set it.

You don't specify the receipt's owner; the service takes it from the token.

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

The response is the saved receipt. Each item shows its category name instead of the id, and next to the receipt total there are two computed fields: `calculated_total`, the sum of the items, and `discrepancy`, the difference between that sum and the total. A positive `discrepancy` means the items together cost more than the receipt says.

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

If the receipt has no total, `discrepancy` is `null`, since there's nothing to compare against.

Receipts come back in pages; set the page size and offset with `limit` and `offset`. By default you get the twenty most recent receipts, newest first.

```
GET /receipts?limit=20&offset=0
```

Spending summary. Groups items by category over a period and sorts by amount. The bounds are optional; without them it covers all time.

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

The start of the period is included and the end isn't. That way neighbouring periods don't overlap and a receipt on the boundary isn't counted twice. Items without a category get their own row with `category_name` set to `null`.

## Data schema

Four tables:

- `users`: email (unique), password hash, registration time;
- `receipts`: the receipt itself, meaning its owner, purchase time, shop and total;
- `items`: the receipt's line items, pointing to the receipt and, if set, to a category;
- `categories`: the list of categories, shared by all users.

Items are read with a `LEFT JOIN` on categories, so an item without a category doesn't disappear from the response; its `category_name` is just empty.

The category list is filled by a migration: sixteen categories, enough for an ordinary supermarket receipt. New ones are added through the API, and text parsing works with whatever is in the database at the moment of the request.

## Design decisions

**Passwords are stored only as argon2 hashes.** The password itself is never saved. Argon2 is deliberately slow and memory-hungry, so brute-forcing passwords from a leaked database takes a lot of time and money. The hash never appears in API responses: user data has its own response model that simply doesn't include it.

**JWT instead of sessions.** The token holds the user id and an expiry time, signed with a secret key. To check a request, the server only verifies the signature and doesn't need to hit the database. The downside of JWT is that an issued token can't be revoked before it expires, which is why the lifetime is short, 15 minutes.

**The receipt's owner comes from the token.** There is no `user_id` field in the request body. If there were, anyone could put in someone else's id and create receipts in their name. The server reads the id from the signed token, and the client can't change it.

**Someone else's receipt returns 404, not 403.** A 403 would say "this receipt exists, but it isn't yours", confirming that it exists, and by walking through ids you could find out how many receipts there are. A 404 looks the same for a receipt that belongs to someone else and one that doesn't exist, so it gives nothing away. Every receipt query filters by `user_id` right in SQL, so the code never even touches other people's data.

**The same answer for a wrong email and a wrong password.** If "no such email" and "wrong password" were different responses, you could check whether a particular person has an account. So both cases return the same thing: 401, "wrong email or password".

**Separate models for registration and sign-in.** Registration checks that the password is 8 to 128 characters long. Sign-in only checks the upper limit. If sign-in also enforced the minimum, a short password would get a 422 instead of a 401, and the response would hint at the password rules. The upper limit applies everywhere: argon2 is slow, and a password several megabytes long would tie up the server.

**Which foreign key failed is read from the constraint name.** When a receipt is created, the database can refuse for two reasons: the category doesn't exist, or the user doesn't exist (for example, they were deleted while their token was still valid). Postgres reports which constraint failed, and based on its name the service answers 400 in the first case and 401 in the second.

**NUMERIC instead of float for money.** `float` stores numbers in binary, and some decimal fractions can't be written in it exactly. That's where the classic `0.1 + 0.2 = 0.30000000000000004` comes from. On one receipt you won't notice, but across many transactions the error adds up. `NUMERIC` stores decimals exactly.

**Two queries instead of N+1 when reading a list.** If you fetch the receipts and then query each receipt's items in a loop, twenty receipts cost twenty-one database queries. Here it's always two: first the receipts, then the items for all of them at once with `ANY`, grouped by receipt in Python. A single query with a `JOIN` doesn't fit either: the receipt data would repeat on every row, and the nested structure would still have to be built by hand.

**TIMESTAMPTZ instead of TIMESTAMP.** `TIMESTAMPTZ` stores a point in time in UTC and returns it in whatever time zone is needed. `TIMESTAMP` stores just the numbers on the clock with no zone, so two moments from different zones become indistinguishable. That's why both the purchase time and the period bounds are accepted only with an explicit time zone. Otherwise the database would fill in the zone from the connection settings, and the result would depend on how the server is configured.

**Validation on two levels.** Pydantic rejects bad data at the API boundary and returns a 422 naming the field. `CHECK` constraints in the database keep garbage out of the tables even if someone writes to them bypassing the API, from a script or psql.

**Connection pool.** Opening a connection to Postgres takes tens of milliseconds, while a query itself takes about one. Opening a connection per request would spend almost the whole response time on that, and under load the database would drown in new processes. The pool keeps connections ready: a request takes a free one, does its work and gives it back.

**Language model failures.** A request to the model can fail in many ways: a timeout, a rate limit, an error on their side, a response in an unexpected format. All of this comes down to two exceptions of our own: "the text couldn't be parsed" and "the service is unavailable". The client gets a 422 or a 503 and knows whether retrying makes sense. The call to the model is async, so while the service waits for an answer it keeps serving other requests.

**Categories only from the list.** If the model could name categories freely, the list would fill up with synonyms like "food", "groceries", "nutrition", and the stats built on them would fall apart. So the model gets the list of existing categories and picks only from it. If nothing fits, the item stays without a category. A separate "other" category would be indistinguishable from the case where the model simply failed.

**Caching parse results.** A request to the model costs money and takes a few seconds, while the same text always parses the same way. The result goes into Redis for a day, keyed by a hash of the text together with the category list: if the list changes, the old result is no longer valid because it holds old ids. The expiry is there for a different reason: the prompt and the model change over time, and a record kept forever would eventually return a result built by rules the code no longer has. The service works without Redis too; it just goes to the model every time and answers more slowly.

**Indexes.** The summary selects receipts by `purchased_at`, the list is sorted by it, and every receipt query filters by `user_id`. Both columns are indexed. Without the indexes the database would read the whole table and check every row. With a thousand receipts you won't notice; with a million it takes seconds. The price of an index is disk space and slightly slower inserts.

## Tests

```bash
pip install -r requirements-dev.txt
DATABASE_URL="postgresql://postgres:secret@localhost:5433/receipts_test" alembic upgrade head
pytest
```

The test database address is passed explicitly because `.env` points to the main one, and the schema has to be applied to both. The tests themselves take the database address, the Redis address and a test `JWT_SECRET` from `pytest.ini` and never touch the main database.

What's covered:

- creating and reading receipts, pagination, categories, discrepancy calculation, the period summary;
- input validation and error codes;
- text parsing, with the model replaced by a fake so the tests never call OpenAI;
- registration, sign-in, `/me`, a duplicate email in any letter case, email and password length right at the limit and one step past it;
- that the password hash never shows up in any response;
- that every protected endpoint returns 401 without a token;
- broken tokens: garbage instead of a token, a token with one character changed, a token signed with a different key, one without `sub` and one with a non-numeric `sub`, plus an expired token and malformed headers;
- that a user can't see someone else's receipt by id, in the list or in the summary.

Before each test the tables and the cache are cleared; the cache lives in a separate Redis database. Before each test a user is also created automatically and their token is added to requests. Tests that need no such user are marked `@pytest.mark.no_auth`. Test order and repeated runs don't affect the results.

CI runs ruff, mypy, the migrations and all tests on every push.

## Plans

- Refresh tokens, so you don't have to sign in every 15 minutes, and sign-out that revokes the token.
- Editing and deleting receipts.
- Rate limiting for sign-in attempts and model requests.
- Running the whole service with a single Docker command.

## License

MIT, see [LICENSE](LICENSE).
