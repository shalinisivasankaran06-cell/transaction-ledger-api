from fastapi import FastAPI
from sqlalchemy import text

from app.db import engine
from app.errors import register_exception_handlers
from app.routers import accounts, transfers

app = FastAPI(
    title="Transaction Ledger API",
    version="1.0.0",
    description=(
        "Accounts with credit/debit transactions, balances and paginated history.\n\n"
        "Money values are decimal strings with 2 places (e.g. \"100.50\"). "
        "Every error has the shape `{\"error\": {\"code\", \"message\", \"details\"}}`."
    ),
)

register_exception_handlers(app)
app.include_router(accounts.router)
app.include_router(transfers.router)


@app.get("/health", tags=["health"], summary="Liveness + database check")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
