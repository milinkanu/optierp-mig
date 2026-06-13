"""Module 05 — Selling Pydantic schemas (shares order bases with buying)."""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import Field

from app.schemas.accounts import InvoiceTaxResponse
from app.schemas.buying import OrderCreateBase, OrderItemResponse, OrderResponseBase

# --- quotation -------------------------------------------------------------------------


class QuotationCreate(OrderCreateBase):
    customer_id: uuid.UUID
    valid_till: date | None = None


class QuotationItemResponse(OrderItemResponse):
    pass


class QuotationResponse(OrderResponseBase):
    customer_id: uuid.UUID
    customer_name: str | None = None
    valid_till: date | None
    items: list[QuotationItemResponse]
    taxes: list[InvoiceTaxResponse]


# --- sales order -----------------------------------------------------------------------


class SalesOrderCreate(OrderCreateBase):
    customer_id: uuid.UUID
    delivery_date: date | None = None
    set_warehouse_id: uuid.UUID | None = None
    quotation_id: uuid.UUID | None = None


class SalesOrderItemResponse(OrderItemResponse):
    delivery_date: date | None = None
    delivered_qty: Decimal
    billed_amt: Decimal
    quotation_item_id: uuid.UUID | None = None


class SalesOrderResponse(OrderResponseBase):
    customer_id: uuid.UUID
    customer_name: str | None = None
    delivery_date: date | None
    set_warehouse_id: uuid.UUID | None
    quotation_id: uuid.UUID | None
    per_delivered: Decimal
    per_billed: Decimal
    items: list[SalesOrderItemResponse]
    taxes: list[InvoiceTaxResponse]
    # transient: filled by the submit endpoint (credit-limit check, Module 05 rule 3)
    warnings: list[str] = Field(default_factory=list)
