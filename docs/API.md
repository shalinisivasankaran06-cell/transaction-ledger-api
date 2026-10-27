# API Reference

Base URL (local): `http://localhost:8000`
Swagger UI: `/docs`, ReDoc: `/redoc`, spec: [openapi.json](openapi.json)

All bodies are JSON. IDs are UUIDs. Money is a decimal string with 2 places (`"100.00"`);
requests can send a number (`100`, `10.5`) or a string (`"10.50"`).

Error format:

```json
{"error": {"code": "SOME_CODE", "message": "Human readable text", "details": {}}}
```

`details` is included for field errors, duplicates (existing transaction) and insufficient balance.


## 1. Create account

`POST /accounts`

| Field | Type | Rules |
|---|---|---|
| `name` | string | required, 1–100 chars after trimming |

`balance`, `id` and `created_at` are set by the system; sending them is a `422`.

```http
POST /accounts
{"name": "Shalini"}
```

`201 Created`
```json
{"id": "c6f5b8f6-8b1f-4472-a287-6e2c4a346cd9", "name": "Shalini", "balance": "0.00",
 "created_at": "2026-10-26T11:38:48.458450Z"}
```

Sending `balance` → `422`
```json
{"error": {"code": "VALIDATION_ERROR", "message": "body.balance: Extra inputs are not permitted",
           "details": [{"field": "body.balance", "message": "Extra inputs are not permitted"}]}}
```


## 2. Get account

`GET /accounts/{account_id}` → `200` with the same shape as above, `404 ACCOUNT_NOT_FOUND` if missing.


## 3. Get balance

`GET /accounts/{account_id}/balance`

`200 OK`
```json
{"account_id": "c6f5b8f6-8b1f-4472-a287-6e2c4a346cd9", "balance": "70.00"}
```

`404 Not Found`
```json
{"error": {"code": "ACCOUNT_NOT_FOUND",
           "message": "Account 00000000-0000-0000-0000-000000000000 not found",
           "details": {"account_id": "00000000-0000-0000-0000-000000000000"}}}
```

An id that is not a UUID (e.g. `/accounts/abc/balance`) → `422 VALIDATION_ERROR`.


## 4. Add transaction

`POST /accounts/{account_id}/transactions`

| Field | Type | Rules |
|---|---|---|
| `type` | string | `"credit"` or `"debit"` (lowercase) |
| `amount` | decimal | > 0, max 2 decimal places, max 16 digits before the point |
| `reference_id` | string | required, 1–100 chars, unique per account |
| `description` | string | optional, max 255 chars |

```http
POST /accounts/c6f5b8f6-.../transactions
{"type": "credit", "amount": 100, "reference_id": "T1", "description": "Salary"}
```

`201 Created`
```json
{"id": "619f3d03-1255-4dd3-b442-c9f09ab43ea5",
 "account_id": "c6f5b8f6-8b1f-4472-a287-6e2c4a346cd9",
 "type": "credit", "amount": "100.00", "description": "Salary", "reference_id": "T1",
 "balance_after": "100.00", "transfer_id": null,
 "created_at": "2026-10-26T11:38:48.534522Z"}
```

`balance_after` is the account balance right after this transaction. `transfer_id` is set
only for the two legs of a transfer.

Insufficient balance (balance 70, debit 500) → `400`, nothing stored
```json
{"error": {"code": "INSUFFICIENT_BALANCE", "message": "Insufficient balance for this debit",
           "details": {"account_id": "c6f5b8f6-...", "balance": "70.00", "requested_amount": "500.00"}}}
```

Duplicate `reference_id` on the same account → `409`, nothing stored
```json
{"error": {"code": "DUPLICATE_TRANSACTION",
           "message": "A transaction with this reference_id already exists for this account",
           "details": {"existing_transaction": {"id": "619f3d03-...", "type": "credit", "amount": "100.00",
                                                "reference_id": "T1", "...": "..."}}}}
```

Validation error (`{"type": "refund", "amount": -1, "reference_id": "T4"}`) → `422`
```json
{"error": {"code": "VALIDATION_ERROR", "message": "body.type: Input should be 'credit' or 'debit'",
           "details": [{"field": "body.type", "message": "Input should be 'credit' or 'debit'"},
                       {"field": "body.amount", "message": "Input should be greater than 0"}]}}
```

Unknown account → `404 ACCOUNT_NOT_FOUND`. Invalid JSON → `422 INVALID_REQUEST_BODY`.


## 5. Transaction history

`GET /accounts/{account_id}/transactions`

| Query | Default | Rules |
|---|---|---|
| `type` | (both) | `credit` or `debit` |
| `page` | `1` | integer ≥ 1 |
| `limit` | `10` | integer 1–100 |

Sorted newest first (`created_at DESC`).

```http
GET /accounts/c6f5b8f6-.../transactions?type=debit&page=1&limit=10
```

`200 OK`
```json
{"data": [
   {"id": "1e2062d0-4274-4f00-8f63-a19605a32c1c", "account_id": "c6f5b8f6-...", "type": "debit",
    "amount": "30.00", "description": null, "reference_id": "T2", "balance_after": "70.00",
    "transfer_id": null, "created_at": "2026-10-26T11:38:48.546952Z"}
 ],
 "pagination": {"page": 1, "limit": 10, "total_records": 1, "total_pages": 1}}
```

A page past the end returns `"data": []` with the totals.

Bad pagination (`?page=0`, `?limit=500`, `?page=abc`) → `400`
```json
{"error": {"code": "INVALID_PAGINATION",
           "message": "page must be an integer >= 1 and limit an integer between 1 and the maximum page size",
           "details": [{"field": "query.page", "message": "Input should be greater than or equal to 1"}]}}
```

Bad type filter (`?type=refund`) → `422 VALIDATION_ERROR`. Unknown account → `404`.


## 6. Transfer

`POST /transfers`

| Field | Type | Rules |
|---|---|---|
| `from_account_id` | UUID | must exist, needs enough balance |
| `to_account_id` | UUID | must exist, different from `from_account_id` |
| `amount` | decimal | > 0, max 2 decimal places |
| `reference_id` | string | required; used on both legs, must be unused on both accounts |
| `description` | string | optional (defaults to "Transfer <from> -> <to>") |

```http
POST /transfers
{"from_account_id": "c6f5b8f6-...", "to_account_id": "c176ad07-...", "amount": 20, "reference_id": "TR1"}
```

`201 Created`
```json
{"transfer_id": "6ff30256-d268-4d5d-a054-dd2a8fd83365",
 "from_account_id": "c6f5b8f6-...", "to_account_id": "c176ad07-...",
 "amount": "20.00", "reference_id": "TR1",
 "debit_transaction":  {"id": "63401086-...", "account_id": "c6f5b8f6-...", "type": "debit",
                        "amount": "20.00", "balance_after": "50.00", "transfer_id": "6ff30256-...", "...": "..."},
 "credit_transaction": {"id": "e519e483-...", "account_id": "c176ad07-...", "type": "credit",
                        "amount": "20.00", "balance_after": "20.00", "transfer_id": "6ff30256-...", "...": "..."}}
```

Errors: `404 ACCOUNT_NOT_FOUND` (either account), `400 INSUFFICIENT_BALANCE`,
`409 DUPLICATE_TRANSACTION`, `422 VALIDATION_ERROR` (including same source and destination).
On any error neither account is changed.


## 7. Health

`GET /health` → `200 {"status": "ok"}` (also checks the database connection).


## Immutability

No endpoint updates or deletes a transaction. `PUT`, `PATCH`, `DELETE` on
`/accounts/{id}/transactions` → `405 METHOD_NOT_ALLOWED`.
