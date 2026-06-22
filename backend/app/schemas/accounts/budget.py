"""Accounts schemas — Budget + Period Closing."""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import DocumentMeta

class PeriodClosingCreate(BaseModel):
    posting_date: date
    fiscal_year_id: uuid.UUID
    closing_account_id: uuid.UUID
    remarks: str | None = None


class PeriodClosingResponse(DocumentMeta):
    name: str
    posting_date: date
    fiscal_year_id: uuid.UUID
    closing_account_id: uuid.UUID
    remarks: str | None
    company_id: uuid.UUID


# --- GL / Reports ----------------------------------------------------------------------------


class BudgetAccountIn(BaseModel):
    account_id: uuid.UUID
    budget_amount: Decimal = Field(gt=0)


class BudgetCreate(BaseModel):
    fiscal_year_id: uuid.UUID
    cost_center_id: uuid.UUID | None = None  # None = company-wide budget
    action_if_annual_budget_exceeded: str = Field(default="Warn", pattern="^(Stop|Warn|Ignore)$")
    # Optional monthly seasonality — when set, a month-to-date cap is also enforced.
    monthly_distribution_id: uuid.UUID | None = None
    action_if_accumulated_monthly_budget_exceeded: str = Field(
        default="Ignore", pattern="^(Stop|Warn|Ignore)$"
    )
    accounts: list[BudgetAccountIn] = Field(min_length=1)


class BudgetAccountResponse(DocumentMeta):
    account_id: uuid.UUID
    budget_amount: Decimal


class BudgetResponse(DocumentMeta):
    fiscal_year_id: uuid.UUID
    cost_center_id: uuid.UUID | None
    action_if_annual_budget_exceeded: str
    monthly_distribution_id: uuid.UUID | None
    action_if_accumulated_monthly_budget_exceeded: str
    company_id: uuid.UUID
    accounts: list[BudgetAccountResponse]


# --- Payment Reconciliation --------------------------------------------------------------------


