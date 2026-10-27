# Transaction Ledger API

REST API for a simple ledger. You can create accounts, post credit/debit transactions, check balances, page through transaction history and transfer money between two accounts.

Stack: Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2, PostgreSQL, Alembic, pytest.

Assumptions I made are listed in [ASSUMPTIONS.md](ASSUMPTIONS.md). Endpoint details with example requests/responses are in [docs/API.md](docs/API.md). Swagger UI is at `/docs` once the app is running.

## Running

### With Docker

```bash
docker compose up --build
```

This starts Postgres 16 and the API on http://localhost:8000 and runs the migration on startup. Postgres is mapped to port 5433 on the host.

Tests inside the container:

```bash
docker compose exec api pytest
```

### Without Docker

Needs Python 3.11+ and PostgreSQL 14+.

```bash
createdb -U postgres ledger
createdb -U postgres ledger_test

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env    # change DATABASE_URL if needed
alembic upgrade head
uvicorn app.main:app --reload
```

### Config

| Variable | Default |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/ledger` |
| `TEST_DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/ledger_test` |
| `DEFAULT_PAGE_SIZE` | `10` |
| `MAX_PAGE_SIZE` | `100` |
| `SQL_ECHO` | `false` |

## Screenshots

Running locally with `docker compose up --build`. Postgres starts, the migration runs and the API comes up on port 8000:

![docker compose up](docs/screenshots/docker-compose-up.jpg)

Swagger UI at http://localhost:8000/docs:

![Swagger UI](docs/screenshots/swagger-ui.jpg)

## Tests

```bash
pytest
```

72 tests. They run against a real Postgres database (`TEST_DATABASE_URL`, tables get dropped and recreated) because the locking and constraint behaviour is what I wanted to test, and SQLite doesn't behave the same way. Besides the normal cases there are tests for a failure halfway through a transfer, 20 parallel debits on one account, 15 parallel requests with the same reference_id, and opposite transfers running at the same time.

## Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/accounts` | Create account, balance starts at 0 |
| GET | `/accounts/{account_id}` | Account details |
| GET | `/accounts/{account_id}/balance` | Current balance |
| POST | `/accounts/{account_id}/transactions` | Add a credit or debit |
| GET | `/accounts/{account_id}/transactions` | History, newest first. Query params: `type`, `page`, `limit` |
| POST | `/transfers` | Transfer between two accounts |
| GET | `/health` | Health check (also pings the DB) |

Transactions can't be edited or deleted. PUT/PATCH/DELETE return 405.

Example:

```bash
curl -X POST localhost:8000/accounts -H 'Content-Type: application/json' -d '{"name":"Shalini"}'

curl -X POST localhost:8000/accounts/<id>/transactions -H 'Content-Type: application/json' \
     -d '{"type":"credit","amount":100,"reference_id":"T1","description":"Salary"}'

curl localhost:8000/accounts/<id>/balance
```

Errors all use the same format:

```json
{"error": {"code": "INSUFFICIENT_BALANCE", "message": "Insufficient balance for this debit", "details": {...}}}
```

Error codes: `ACCOUNT_NOT_FOUND` (404), `VALIDATION_ERROR` (422), `INVALID_REQUEST_BODY` (422), `INSUFFICIENT_BALANCE` (400), `DUPLICATE_TRANSACTION` (409), `INVALID_PAGINATION` (400), `METHOD_NOT_ALLOWED` (405), `INTERNAL_ERROR` (500).

## Project layout

```
app/
  main.py           app setup, /health
  config.py         settings from env
  db.py             engine and session
  models.py         Account, Transaction
  schemas.py        request/response models
  errors.py         error classes and handlers
  routers/          accounts.py, transfers.py
  services/         account, transaction and transfer logic
alembic/            migration
tests/
scripts/            export_openapi.py, init-test-db.sql
docs/               API.md, openapi.json
```

## Design notes

Each transaction is one DB transaction: the balance update and the transaction insert are committed together or rolled back together, so the stored balance always matches the sum of the transactions.

To handle concurrent requests on the same account I lock the account row with `SELECT ... FOR UPDATE` before reading the balance. Without it two debits can both read the same balance and overdraw the account. For transfers I lock both accounts in id order so that A->B and B->A at the same time can't deadlock.

`reference_id` is unique per account. I check for it in code after taking the lock (so the client gets a 409 with the existing transaction) and there is also a unique constraint on `(account_id, reference_id)`. Rejected transactions aren't saved, so their reference_id can be reused.

The database also has its own checks: `balance >= 0`, `amount > 0`, type is credit/debit, plus a foreign key and NOT NULLs.

Amounts are `NUMERIC(18,2)` in Postgres and `Decimal` in Python, not float. Amounts with more than 2 decimal places are rejected. Money is returned as a string (`"70.00"`).

Request models use `extra="forbid"`, so a client can't send `balance`, `id` or `created_at`.

History uses OFFSET/LIMIT ordered by `created_at DESC, id DESC`, with an index on `(account_id, created_at)`.
