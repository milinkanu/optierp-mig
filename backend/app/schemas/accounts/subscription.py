"""Module 02 (Accounts) schemas — Subscription (recurring billing).

The Subscription Plan master is served by the metadata engine (no schema here);
these cover the bespoke Subscription document + its plan rows and the result of a
manual invoice-generation run.
"""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import DocumentMeta, ORMModel


class SubscriptionPlanDetailIn(BaseModel):
    plan_id: uuid.UUID
    qty: Decimal = Field(gt=0, default=Decimal("1"))


class SubscriptionCreate(BaseModel):
    customer_id: uuid.UUID
    start_date: date
    end_date: date | None = None
    days_until_due: int = Field(ge=0, default=0)
    generate_at: str = "Beginning"  # Beginning | End
    # the first invoice date; defaults to start_date when omitted
    next_invoice_date: date | None = None
    plans: list[SubscriptionPlanDetailIn] = Field(min_length=1)


class SubscriptionPlanDetailResponse(ORMModel):
    id: uuid.UUID
    idx: int
    plan_id: uuid.UUID
    qty: Decimal


class SubscriptionResponse(DocumentMeta):
    name: str
    customer_id: uuid.UUID
    customer_name: str | None
    start_date: date
    end_date: date | None
    status: str
    days_until_due: int
    generate_at: str
    next_invoice_date: date
    last_invoice_date: date | None
    company_id: uuid.UUID
    plans: list[SubscriptionPlanDetailResponse]


class SubscriptionListItem(ORMModel):
    id: uuid.UUID
    name: str
    customer_name: str | None
    status: str
    start_date: date
    end_date: date | None
    next_invoice_date: date


class GenerateInvoiceResult(BaseModel):
    """Outcome of a (manual or scheduled) invoice-generation run for one subscription."""

    generated: bool
    invoice_id: uuid.UUID | None = None
    invoice_name: str | None = None
    detail: str | None = None  # why nothing was generated (not due / completed / cancelled)
