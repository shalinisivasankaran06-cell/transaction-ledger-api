import uuid

from sqlalchemy import func, select

from app.models import Transaction, TransactionType
from app.services import transfer_service


def transfer(client, src, dst, amount, ref="T-1", **extra):
    return client.post("/transfers", json={"from_account_id": src, "to_account_id": dst,
                                           "amount": amount, "reference_id": ref, **extra})


def test_transfer_moves_money(client, make_account, balance_of):
    a, b = make_account("A", credit="100"), make_account("B", credit="50")
    resp = transfer(client, a["id"], b["id"], "30", description="Dinner split")
    assert resp.status_code == 201
    body = resp.json()
    assert body["amount"] == "30.00"
    assert body["debit_transaction"]["type"] == "debit"
    assert body["debit_transaction"]["account_id"] == a["id"]
    assert body["credit_transaction"]["type"] == "credit"
    assert body["credit_transaction"]["account_id"] == b["id"]
    assert body["debit_transaction"]["transfer_id"] == body["credit_transaction"]["transfer_id"] == body["transfer_id"]
    assert balance_of(a["id"]) == "70.00"
    assert balance_of(b["id"]) == "80.00"


def test_transfer_shows_in_both_histories(client, make_account):
    a, b = make_account("A", credit="100"), make_account("B")
    transfer(client, a["id"], b["id"], "30")
    assert client.get(f"/accounts/{a['id']}/transactions", params={"type": "debit"}).json()["pagination"]["total_records"] == 1
    assert client.get(f"/accounts/{b['id']}/transactions", params={"type": "credit"}).json()["pagination"]["total_records"] == 1


def test_transfer_insufficient_balance_changes_nothing(client, make_account, balance_of, db):
    a, b = make_account("A", credit="100"), make_account("B", credit="50")
    resp = transfer(client, a["id"], b["id"], "150")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INSUFFICIENT_BALANCE"
    assert balance_of(a["id"]) == "100.00"
    assert balance_of(b["id"]) == "50.00"
    assert db.scalar(select(func.count()).select_from(Transaction).where(Transaction.transfer_id.is_not(None))) == 0


def test_transfer_unknown_source_or_destination(client, make_account, balance_of):
    a = make_account("A", credit="100")
    missing = str(uuid.uuid4())
    r1 = transfer(client, a["id"], missing, "10")
    r2 = transfer(client, missing, a["id"], "10")
    assert r1.status_code == r2.status_code == 404
    assert r1.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"
    assert balance_of(a["id"]) == "100.00"


def test_transfer_to_same_account_rejected(client, make_account):
    a = make_account("A", credit="100")
    resp = transfer(client, a["id"], a["id"], "10")
    assert resp.status_code == 422


def test_transfer_invalid_amount(client, make_account):
    a, b = make_account("A", credit="100"), make_account("B")
    assert transfer(client, a["id"], b["id"], "-5").status_code == 422
    assert transfer(client, a["id"], b["id"], 0).status_code == 422


def test_duplicate_transfer_is_409_and_not_applied_twice(client, make_account, balance_of):
    a, b = make_account("A", credit="100"), make_account("B")
    assert transfer(client, a["id"], b["id"], "30", ref="T-9").status_code == 201
    dup = transfer(client, a["id"], b["id"], "30", ref="T-9")
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "DUPLICATE_TRANSACTION"
    assert balance_of(a["id"]) == "70.00"
    assert balance_of(b["id"]) == "30.00"


def test_destination_reference_clash_rolls_back_the_debit(client, make_account, balance_of):
    # B already has reference X, so the credit leg fails after the debit leg went through
    a, b = make_account("A", credit="100"), make_account("B")
    client.post(f"/accounts/{b['id']}/transactions", json={"type": "credit", "amount": "1", "reference_id": "X"})
    resp = transfer(client, a["id"], b["id"], "30", ref="X")
    assert resp.status_code == 409
    assert balance_of(a["id"]) == "100.00"
    assert balance_of(b["id"]) == "1.00"


def test_failure_after_debit_rolls_back_everything(client, make_account, balance_of, db, monkeypatch):
    # simulate a failure between the debit and the credit
    a, b = make_account("A", credit="100"), make_account("B", credit="50")
    real_apply = transfer_service.apply_transaction

    def flaky_apply(db_, account, type_, *args, **kwargs):
        if type_ is TransactionType.CREDIT:
            raise RuntimeError("simulated failure after the debit was written")
        return real_apply(db_, account, type_, *args, **kwargs)

    monkeypatch.setattr(transfer_service, "apply_transaction", flaky_apply)
    resp = transfer(client, a["id"], b["id"], "30")
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "INTERNAL_ERROR"

    assert balance_of(a["id"]) == "100.00"
    assert balance_of(b["id"]) == "50.00"
    assert db.scalar(select(func.count()).select_from(Transaction).where(Transaction.transfer_id.is_not(None))) == 0
