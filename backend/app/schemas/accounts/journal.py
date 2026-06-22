"""Accounts schemas — Journal Entry."""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import DocumentMeta, ORMModel

class JournalEntryAccountIn(BaseModel):
    account_id: uuid.UUID
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    party_type: str | None = None
    party_id: uuid.UUID | None = None
    cost_center_id: uuid.UUID | None = None
    account_currency: str | None = None
    exchange_rate: Decimal = Decimal("1")
    debit_in_account_currency: Decimal | None = None
    credit_in_account_currency: Decimal | None = None
    reference_type: str | None = None
    reference_id: uuid.UUID | None = None
    user_remark: str | None = None

    @field_validator("debit", "credit")
    @classmethod
    def non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("must be >= 0")
        return v


class JournalEntryCreate(BaseModel):
    posting_date: date
    voucher_type: str = "Journal Entry"
    remarks: str | None = None
    multi_currency: bool = False
    accounts: list[JournalEntryAccountIn] = Field(min_length=2)


class JournalEntryAccountResponse(DocumentMeta):
    idx: int
    account_id: uuid.UUID
    debit: Decimal
    credit: Decimal
    party_type: str | None
    party_id: uuid.UUID | None
    cost_center_id: uuid.UUID | None
    reference_type: str | None
    reference_id: uuid.UUID | None
    user_remark: str | None


class JournalEntryResponse(DocumentMeta):
    name: str
    posting_date: date
    voucher_type: str
    total_debit: Decimal
    total_credit: Decimal
    clearance_date: date | None
    remarks: str | None
    workflow_state: str | None
    company_id: uuid.UUID
    accounts: list[JournalEntryAccountResponse]


class JournalEntryListItem(ORMModel):
    id: uuid.UUID
    name: str
    posting_date: date
    voucher_type: str
    total_debit: Decimal
    docstatus: int


# --- Invoices ---------------------------------------------------------------------------


