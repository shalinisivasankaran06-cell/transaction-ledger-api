import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import TransactionType
from app.schemas import (
    AccountCreate,
    AccountOut,
    BalanceOut,
    ErrorResponse,
    PaginationMeta,
    TransactionCreate,
    TransactionOut,
    TransactionPage,
)
from app.services import account_service, transaction_service

router = APIRouter(prefix="/accounts", tags=["accounts"])

DbSession = Annotated[Session, Depends(get_db)]

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Account not found"}}
INVALID = {422: {"model": ErrorResponse, "description": "Validation error"}}


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED, responses=INVALID,
             summary="Create an account (balance starts at 0)")
def create_account(payload: AccountCreate, db: DbSession):
    return account_service.create_account(db, payload.name)


@router.get("/{account_id}", response_model=AccountOut, responses={**NOT_FOUND, **INVALID},
            summary="Get account details")
def get_account(account_id: uuid.UUID, db: DbSession):
    return account_service.get_account(db, account_id)


@router.get("/{account_id}/balance", response_model=BalanceOut, responses={**NOT_FOUND, **INVALID},
            summary="Get the current balance")
def get_balance(account_id: uuid.UUID, db: DbSession):
    account = account_service.get_account(db, account_id)
    return BalanceOut(account_id=account.id, balance=account.balance)


@router.post(
    "/{account_id}/transactions",
    response_model=TransactionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a credit or debit transaction",
    responses={
        **NOT_FOUND,
        **INVALID,
        400: {"model": ErrorResponse, "description": "Insufficient balance (debit rejected, balance unchanged)"},
        409: {"model": ErrorResponse, "description": "reference_id already used on this account (existing transaction in details)"},
    },
)
def add_transaction(account_id: uuid.UUID, payload: TransactionCreate, db: DbSession):
    return transaction_service.create_transaction(db, account_id, payload)


@router.get(
    "/{account_id}/transactions",
    response_model=TransactionPage,
    summary="Transaction history (newest first, filter by type, paginated)",
    responses={**NOT_FOUND, **INVALID, 400: {"model": ErrorResponse, "description": "Invalid pagination parameters"}},
)
def list_transactions(
    account_id: uuid.UUID,
    db: DbSession,
    type: Annotated[TransactionType | None, Query(description="credit or debit; omit for both")] = None,
    page: Annotated[int, Query(ge=1, description="Page number, starting at 1")] = 1,
    limit: Annotated[int, Query(ge=1, le=settings.max_page_size, description="Records per page")] = settings.default_page_size,
):
    rows, total = transaction_service.list_transactions(db, account_id, type, page, limit)
    return TransactionPage(
        data=[TransactionOut.model_validate(r) for r in rows],
        pagination=PaginationMeta(
            page=page, limit=limit, total_records=total, total_pages=transaction_service.total_pages(total, limit)
        ),
    )
