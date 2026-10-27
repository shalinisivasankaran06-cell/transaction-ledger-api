from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import ErrorResponse, TransferCreate, TransferOut
from app.services import transfer_service

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.post(
    "",
    response_model=TransferOut,
    status_code=status.HTTP_201_CREATED,
    summary="Transfer money from one account to another (atomic)",
    responses={
        400: {"model": ErrorResponse, "description": "Insufficient balance in the source account"},
        404: {"model": ErrorResponse, "description": "Source or destination account not found"},
        409: {"model": ErrorResponse, "description": "reference_id already used on one of the accounts"},
        422: {"model": ErrorResponse, "description": "Validation error"},
    },
)
def create_transfer(payload: TransferCreate, db: Annotated[Session, Depends(get_db)]):
    return transfer_service.create_transfer(db, payload)
