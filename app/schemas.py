import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models import TransactionType

PositiveAmount = Annotated[
    Decimal,
    Field(gt=0, max_digits=18, decimal_places=2, examples=["100.00"]),
    AfterValidator(lambda v: v.quantize(Decimal("0.01"))),
]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
ReferenceId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]


class RequestModel(BaseModel):
    # reject unknown fields so clients can't set balance/id/created_at
    model_config = ConfigDict(extra="forbid")


class AccountCreate(RequestModel):
    name: Name = Field(examples=["Shalini"])


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    balance: Decimal
    created_at: datetime


class BalanceOut(BaseModel):
    account_id: uuid.UUID
    balance: Decimal


class TransactionCreate(RequestModel):
    type: TransactionType = Field(examples=["credit"])
    amount: PositiveAmount
    reference_id: ReferenceId = Field(examples=["TXN-1001"])
    description: Description | None = Field(default=None, examples=["Salary"])


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    type: TransactionType
    amount: Decimal
    description: str | None
    reference_id: str
    balance_after: Decimal
    transfer_id: uuid.UUID | None
    created_at: datetime


class PaginationMeta(BaseModel):
    page: int
    limit: int
    total_records: int
    total_pages: int


class TransactionPage(BaseModel):
    data: list[TransactionOut]
    pagination: PaginationMeta


class TransferCreate(RequestModel):
    from_account_id: uuid.UUID
    to_account_id: uuid.UUID
    amount: PositiveAmount
    reference_id: ReferenceId = Field(examples=["TRF-2001"])
    description: Description | None = Field(default=None, examples=["Rent share"])

    @model_validator(mode="after")
    def accounts_must_differ(self):
        if self.from_account_id == self.to_account_id:
            raise ValueError("from_account_id and to_account_id must be different accounts")
        return self


class TransferOut(BaseModel):
    transfer_id: uuid.UUID
    from_account_id: uuid.UUID
    to_account_id: uuid.UUID
    amount: Decimal
    reference_id: str
    debit_transaction: TransactionOut
    credit_transaction: TransactionOut


class ErrorBody(BaseModel):
    code: str = Field(examples=["ACCOUNT_NOT_FOUND"])
    message: str = Field(examples=["Account not found"])
    details: dict | list | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
