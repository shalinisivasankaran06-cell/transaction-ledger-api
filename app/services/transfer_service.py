import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import DuplicateTransaction
from app.models import TransactionType
from app.schemas import TransferCreate, TransactionOut
from app.services.account_service import get_account_for_update
from app.services.transaction_service import apply_transaction, find_by_reference


def create_transfer(db: Session, data: TransferCreate):
    transfer_id = uuid.uuid4()
    try:
        # lock in id order so A->B and B->A at the same time can't deadlock
        locked = {}
        for account_id in sorted([data.from_account_id, data.to_account_id]):
            locked[account_id] = get_account_for_update(db, account_id)
        source = locked[data.from_account_id]
        destination = locked[data.to_account_id]

        description = data.description or f"Transfer {source.id} -> {destination.id}"
        debit = apply_transaction(
            db, source, TransactionType.DEBIT, data.amount, data.reference_id, description, transfer_id
        )
        credit = apply_transaction(
            db, destination, TransactionType.CREDIT, data.amount, data.reference_id, description, transfer_id
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        for account_id in (data.from_account_id, data.to_account_id):
            existing = find_by_reference(db, account_id, data.reference_id)
            if existing is not None:
                raise DuplicateTransaction(TransactionOut.model_validate(existing).model_dump(mode="json"))
        raise
    except Exception:
        db.rollback()
        raise

    return {
        "transfer_id": transfer_id,
        "from_account_id": source.id,
        "to_account_id": destination.id,
        "amount": data.amount,
        "reference_id": data.reference_id,
        "debit_transaction": debit,
        "credit_transaction": credit,
    }
