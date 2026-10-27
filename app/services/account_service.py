import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AccountNotFound
from app.models import Account


def create_account(db: Session, name: str) -> Account:
    account = Account(name=name, balance=Decimal("0.00"))
    db.add(account)
    db.commit()
    return account


def get_account(db: Session, account_id: uuid.UUID) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise AccountNotFound(account_id)
    return account


def get_account_for_update(db: Session, account_id: uuid.UUID) -> Account:
    # FOR UPDATE so concurrent debits on the same account wait for each other
    # instead of both reading the old balance
    account = db.execute(select(Account).where(Account.id == account_id).with_for_update()).scalar_one_or_none()
    if account is None:
        raise AccountNotFound(account_id)
    return account
