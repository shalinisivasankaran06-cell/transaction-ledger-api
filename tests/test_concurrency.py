# real threads, each with its own session, so the row locks are actually exercised
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from sqlalchemy import func, select

from app.db import SessionLocal
from app.errors import AppError, DuplicateTransaction, InsufficientBalance
from app.models import Account, Transaction, TransactionType
from app.schemas import TransactionCreate, TransferCreate
from app.services import account_service, transaction_service, transfer_service


def new_account(balance: str) -> uuid.UUID:
    with SessionLocal() as db:
        acc = account_service.create_account(db, "concurrent")
        if Decimal(balance) > 0:
            transaction_service.create_transaction(
                db, acc.id, TransactionCreate(type=TransactionType.CREDIT, amount=balance, reference_id="seed"))
        return acc.id


def balance(account_id) -> Decimal:
    with SessionLocal() as db:
        return db.get(Account, account_id).balance


def run_parallel(fn, n):
    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(fn, range(n)))


def test_parallel_debits_never_overdraw():
    account_id = new_account("100")

    def debit(i):
        with SessionLocal() as db:
            try:
                transaction_service.create_transaction(
                    db, account_id, TransactionCreate(type=TransactionType.DEBIT, amount="30", reference_id=f"d{i}"))
                return "ok"
            except InsufficientBalance:
                return "rejected"

    results = run_parallel(debit, 20)
    assert results.count("ok") == 3          # 3 x 30 = 90 <= 100
    assert results.count("rejected") == 17
    assert balance(account_id) == Decimal("10.00")


def test_parallel_duplicate_reference_applied_once():
    account_id = new_account("0")

    def credit(_):
        with SessionLocal() as db:
            try:
                transaction_service.create_transaction(
                    db, account_id, TransactionCreate(type=TransactionType.CREDIT, amount="10", reference_id="SAME"))
                return "ok"
            except DuplicateTransaction:
                return "duplicate"

    results = run_parallel(credit, 15)
    assert results.count("ok") == 1
    assert results.count("duplicate") == 14
    assert balance(account_id) == Decimal("10.00")


def test_parallel_credits_and_debits_keep_balance_equal_to_sum():
    account_id = new_account("500")

    def work(i):
        type_ = TransactionType.CREDIT if i % 2 else TransactionType.DEBIT
        with SessionLocal() as db:
            try:
                transaction_service.create_transaction(
                    db, account_id, TransactionCreate(type=type_, amount="7.25", reference_id=f"m{i}"))
            except AppError:
                pass

    run_parallel(work, 40)
    with SessionLocal() as db:
        credits = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0))
                            .where(Transaction.account_id == account_id, Transaction.type == "credit"))
        debits = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0))
                           .where(Transaction.account_id == account_id, Transaction.type == "debit"))
    assert balance(account_id) == credits - debits == Decimal("500.00")


def test_opposite_transfers_do_not_deadlock():
    """A->B and B->A at the same time should not deadlock."""
    a, b = new_account("1000"), new_account("1000")

    def move(i):
        src, dst = (a, b) if i % 2 else (b, a)
        with SessionLocal() as db:
            transfer_service.create_transfer(
                db, TransferCreate(from_account_id=src, to_account_id=dst, amount="5", reference_id=f"t{i}"))
        return "ok"

    results = run_parallel(move, 30)
    assert results == ["ok"] * 30
    assert balance(a) + balance(b) == Decimal("2000.00")
    assert balance(a) == balance(b) == Decimal("1000.00")  # 15 each way
