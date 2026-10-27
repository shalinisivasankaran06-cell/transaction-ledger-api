# Tests need a real Postgres database (set TEST_DATABASE_URL). Tables are dropped and recreated.
import os

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/ledger_test"
)
# must be set before app is imported, the engine is created at import time
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    cfg = Config(os.path.join(PROJECT_ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(PROJECT_ROOT, "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables():
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE transactions, accounts CASCADE"))
    yield


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def make_account(client):
    def _make(name="Test User", credit=None):
        resp = client.post("/accounts", json={"name": name})
        assert resp.status_code == 201, resp.text
        account = resp.json()
        if credit is not None:
            r = client.post(
                f"/accounts/{account['id']}/transactions",
                json={"type": "credit", "amount": str(credit), "reference_id": f"seed-{account['id']}"},
            )
            assert r.status_code == 201, r.text
        return account

    return _make


@pytest.fixture
def balance_of(client):
    def _balance(account_id):
        resp = client.get(f"/accounts/{account_id}/balance")
        assert resp.status_code == 200, resp.text
        return resp.json()["balance"]

    return _balance
