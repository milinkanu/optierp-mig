"""Module 02 (Accounts) schemas — Share Management.

Share Type and Shareholder masters are served by the metadata engine (no schema here);
these cover the bespoke Share Transfer document and the derived cap-table / ledger reports.
"""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import DocumentMeta, ORMModel


class ShareTransferCreate(BaseModel):
    transfer_type: str  # Issue | Transfer | Buyback
    share_type_id: uuid.UUID
    from_shareholder_id: uuid.UUID | None = None
    to_shareholder_id: uuid.UUID | None = None
    no_of_shares: int = Field(gt=0)
    rate: Decimal = Field(ge=0, default=Decimal("0"))
    transfer_date: date
    remarks: str | None = None


class ShareTransferResponse(DocumentMeta):
    name: str
    transfer_type: str
    share_type_id: uuid.UUID
    share_type_name: str | None
    from_shareholder_id: uuid.UUID | None
    from_shareholder_name: str | None
    to_shareholder_id: uuid.UUID | None
    to_shareholder_name: str | None
    no_of_shares: int
    rate: Decimal
    amount: Decimal
    transfer_date: date
    status: str
    remarks: str | None
    company_id: uuid.UUID


class ShareTransferListItem(ORMModel):
    id: uuid.UUID
    name: str
    transfer_type: str
    share_type_name: str | None
    from_shareholder_name: str | None
    to_shareholder_name: str | None
    no_of_shares: int
    transfer_date: date
    status: str


class ShareBalanceRow(BaseModel):
    """One shareholder's holding of one share type (the cap table)."""

    shareholder_id: uuid.UUID
    shareholder_name: str
    share_type_id: uuid.UUID
    share_type_name: str
    no_of_shares: int
    par_value: Decimal
    nominal_value: Decimal  # no_of_shares × par_value
    percent_of_type: Decimal  # holding ÷ total issued of that type × 100


class ShareLedgerRow(BaseModel):
    """One submitted transfer, chronological (the share ledger)."""

    id: uuid.UUID
    name: str
    transfer_date: date
    transfer_type: str
    share_type_name: str | None
    from_shareholder_name: str | None
    to_shareholder_name: str | None
    no_of_shares: int
    rate: Decimal
    amount: Decimal
