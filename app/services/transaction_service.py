import math
import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import DuplicateTransaction, InsufficientBalance
from app.models import Account, Transaction, TransactionType
from app.schemas import TransactionCreate, TransactionOut
from app.services.account_service import get_account, get_account_for_update


def find_by_reference(db: Session, account_id: uuid.UUID, reference_id: str) -> Transaction | None:
    return db.execute(
        select(Transaction).where(Transaction.account_id == account_id, Transaction.reference_id == reference_id)
    ).scalar_one_or_none()


def _duplicate_error(txn: Transaction) -> DuplicateTransaction:
    return DuplicateTransaction(TransactionOut.model_validate(txn).model_dump(mode="json"))


def apply_transaction(
    db: Session,
    account: Account,
    type_: TransactionType,
    amount: Decimal,
    reference_id: str,
    description: str | None,
    transfer_id: uuid.UUID | None = None,
) -> Transaction:
    # caller holds the row lock and owns commit/rollback
    existing = find_by_reference(db, account.id, reference_id)
    if existing is not None:
        raise _duplicate_error(existing)

    if type_ is TransactionType.CREDIT:
        new_balance = account.balance + amount
    else:
        if account.balance < amount:
            raise InsufficientBalance(account.id, account.balance, amount)
        new_balance = account.balance - amount

    account.balance = new_balance
    txn = Transaction(
        account_id=account.id,
        type=type_,
        amount=amount,
        reference_id=reference_id,
        description=description,
        balance_after=new_balance,
        transfer_id=transfer_id,
    )
    db.add(txn)
    db.flush()
    return txn


def create_transaction(db: Session, account_id: uuid.UUID, data: TransactionCreate) -> Transaction:
    try:
        account = get_account_for_update(db, account_id)
        txn = apply_transaction(db, account, data.type, data.amount, data.reference_id, data.description)
        db.commit()
        return txn
    except IntegrityError:
        # unique constraint as a backstop in case the duplicate check is ever bypassed
        db.rollback()
        existing = find_by_reference(db, account_id, data.reference_id)
        if existing is not None:
            raise _duplicate_error(existing)
        raise
    except Exception:
        db.rollback()
        raise


def list_transactions(
    db: Session, account_id: uuid.UUID, type_: TransactionType | None, page: int, limit: int
) -> tuple[list[Transaction], int]:
    get_account(db, account_id)

    filters = [Transaction.account_id == account_id]
    if type_ is not None:
        filters.append(Transaction.type == type_)

    total = db.execute(select(func.count()).select_from(Transaction).where(*filters)).scalar_one()
    rows = (
        db.execute(
            select(Transaction)
            .where(*filters)
            # id as tie-breaker so pages stay stable
            .order_by(Transaction.created_at.desc(), Transaction.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return list(rows), total


def total_pages(total_records: int, limit: int) -> int:
    return math.ceil(total_records / limit) if total_records else 0
