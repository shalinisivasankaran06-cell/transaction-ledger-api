import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import Account, Transaction


def post_txn(client, account_id, type_, amount, ref, description=None):
    body = {"type": type_, "amount": amount, "reference_id": ref}
    if description is not None:
        body["description"] = description
    return client.post(f"/accounts/{account_id}/transactions", json=body)


def test_credit_increases_balance(client, make_account, balance_of):
    acc = make_account(credit="100")
    resp = post_txn(client, acc["id"], "credit", "50", "c-1", "Salary")
    assert resp.status_code == 201
    txn = resp.json()
    assert txn["type"] == "credit"
    assert txn["amount"] == "50.00"
    assert txn["description"] == "Salary"
    assert txn["reference_id"] == "c-1"
    assert txn["account_id"] == acc["id"]
    assert txn["balance_after"] == "150.00"
    assert balance_of(acc["id"]) == "150.00"


def test_debit_decreases_balance(client, make_account, balance_of):
    acc = make_account(credit="100")
    resp = post_txn(client, acc["id"], "debit", 30, "d-1")
    assert resp.status_code == 201
    assert balance_of(acc["id"]) == "70.00"


def test_debit_of_entire_balance_allowed(client, make_account, balance_of):
    acc = make_account(credit="100")
    assert post_txn(client, acc["id"], "debit", "100", "d-all").status_code == 201
    assert balance_of(acc["id"]) == "0.00"


def test_insufficient_balance_rejected_and_balance_unchanged(client, make_account, balance_of, db):
    acc = make_account(credit="100")
    resp = post_txn(client, acc["id"], "debit", "150", "d-too-much")
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert err["code"] == "INSUFFICIENT_BALANCE"
    assert err["details"]["balance"] == "100.00"
    assert balance_of(acc["id"]) == "100.00"
    # no transaction row was written for the rejected debit
    count = db.scalar(select(func.count()).select_from(Transaction).where(Transaction.reference_id == "d-too-much"))
    assert count == 0


def test_debit_on_new_account_rejected(client, make_account):
    acc = make_account()
    assert post_txn(client, acc["id"], "debit", "0.01", "d-1").status_code == 400


def test_duplicate_reference_id_same_account(client, make_account, balance_of, db):
    acc = make_account()
    first = post_txn(client, acc["id"], "credit", "100", "REF-1")
    assert first.status_code == 201

    dup = post_txn(client, acc["id"], "credit", "100", "REF-1")
    assert dup.status_code == 409
    err = dup.json()["error"]
    assert err["code"] == "DUPLICATE_TRANSACTION"
    assert "already exists" in err["message"]
    assert err["details"]["existing_transaction"]["id"] == first.json()["id"]

    assert balance_of(acc["id"]) == "100.00"  # balance changed only once
    assert db.scalar(select(func.count()).select_from(Transaction)) == 1


def test_duplicate_with_different_payload_is_still_duplicate(client, make_account, balance_of):
    acc = make_account()
    post_txn(client, acc["id"], "credit", "100", "REF-1")
    dup = post_txn(client, acc["id"], "debit", "40", "REF-1")
    assert dup.status_code == 409
    assert balance_of(acc["id"]) == "100.00"


def test_same_reference_id_allowed_on_different_accounts(client, make_account, balance_of):
    a, b = make_account("A"), make_account("B")
    assert post_txn(client, a["id"], "credit", "10", "SHARED").status_code == 201
    assert post_txn(client, b["id"], "credit", "20", "SHARED").status_code == 201
    assert balance_of(a["id"]) == "10.00"
    assert balance_of(b["id"]) == "20.00"


def test_rejected_debit_does_not_burn_reference_id(client, make_account):
    """A rejected transaction is not stored, so its reference_id can be retried later."""
    acc = make_account()
    assert post_txn(client, acc["id"], "debit", "50", "R").status_code == 400
    assert post_txn(client, acc["id"], "credit", "100", "C").status_code == 201
    assert post_txn(client, acc["id"], "debit", "50", "R").status_code == 201


def test_transaction_on_unknown_account_is_404(client):
    resp = post_txn(client, str(uuid.uuid4()), "credit", "10", "x")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"


@pytest.mark.parametrize("bad_type", ["deposit", "CREDIT", "", None, 1])
def test_invalid_type(client, make_account, bad_type):
    acc = make_account()
    resp = client.post(f"/accounts/{acc['id']}/transactions",
                       json={"type": bad_type, "amount": "10", "reference_id": "r"})
    assert resp.status_code == 422
    assert resp.json()["error"]["details"][0]["field"] == "body.type"


@pytest.mark.parametrize("bad_amount", [0, -5, "0.00", "abc", "10.123", None, "1e30"])
def test_invalid_amount(client, make_account, bad_amount):
    acc = make_account()
    resp = client.post(f"/accounts/{acc['id']}/transactions",
                       json={"type": "credit", "amount": bad_amount, "reference_id": "r"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert resp.json()["error"]["details"][0]["field"] == "body.amount"


@pytest.mark.parametrize("bad_ref", [None, "", "   "])
def test_reference_id_required(client, make_account, bad_ref):
    acc = make_account()
    body = {"type": "credit", "amount": "10"}
    if bad_ref is not None:
        body["reference_id"] = bad_ref
    resp = client.post(f"/accounts/{acc['id']}/transactions", json=body)
    assert resp.status_code == 422
    assert resp.json()["error"]["details"][0]["field"] == "body.reference_id"


def test_unknown_field_rejected(client, make_account):
    acc = make_account()
    resp = client.post(f"/accounts/{acc['id']}/transactions",
                       json={"type": "credit", "amount": "10", "reference_id": "r", "balance_after": "999"})
    assert resp.status_code == 422


def test_balance_equals_sum_of_transactions(client, make_account, balance_of, db):
    """+100 +50 -30 -20 = 100, and a rejected debit changes nothing."""
    acc = make_account()
    for i, (t, amt) in enumerate([("credit", "100"), ("credit", "50"), ("debit", "30"), ("debit", "20")]):
        assert post_txn(client, acc["id"], t, amt, f"r{i}").status_code == 201
    assert post_txn(client, acc["id"], "debit", "1000", "rejected").status_code == 400
    assert balance_of(acc["id"]) == "100.00"

    credits = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0))
                        .where(Transaction.account_id == uuid.UUID(acc["id"]), Transaction.type == "credit"))
    debits = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0))
                       .where(Transaction.account_id == uuid.UUID(acc["id"]), Transaction.type == "debit"))
    assert credits - debits == Decimal("100.00")


def test_decimal_precision_no_float_errors(client, make_account, balance_of):
    acc = make_account()
    post_txn(client, acc["id"], "credit", "0.10", "a")
    post_txn(client, acc["id"], "credit", "0.20", "b")
    assert balance_of(acc["id"]) == "0.30"  # with floats this would be 0.30000000000000004


def test_transactions_are_immutable(client, make_account):
    acc = make_account()
    txn = post_txn(client, acc["id"], "credit", "10", "r").json()
    for method in ("put", "patch", "delete"):
        resp = getattr(client, method)(f"/accounts/{acc['id']}/transactions/{txn['id']}")
        assert resp.status_code in (404, 405)
    for method in ("put", "patch", "delete"):
        resp = getattr(client, method)(f"/accounts/{acc['id']}/transactions")
        assert resp.status_code == 405
        assert resp.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_database_rejects_negative_balance(db, make_account):
    """CHECK constraint blocks a negative balance even when written directly."""
    from sqlalchemy.exc import IntegrityError

    acc = make_account()
    account = db.get(Account, uuid.UUID(acc["id"]))
    account.balance = Decimal("-1")
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
