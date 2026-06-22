"""Module 05 — Selling Pydantic schemas (shares order bases with buying)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schemas.accounts import InvoiceTaxResponse
from app.schemas.buying import OrderCreateBase, OrderItemResponse, OrderResponseBase

OrderType = Literal["Sales", "Maintenance", "Shopping Cart"]

# --- quotation -------------------------------------------------------------------------


class QuotationCreate(OrderCreateBase):
    customer_id: uuid.UUID
    valid_till: date | None = None
    order_type: OrderType = "Sales"
    terms: str | None = None
    customer_address_id: uuid.UUID | None = None
    shipping_address_id: uuid.UUID | None = None
    contact_person_id: uuid.UUID | None = None
    coupon_code: str | None = None
    shipping_rule_id: uuid.UUID | None = None
    # More Info (selling)
    campaign_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    territory_id: uuid.UUID | None = None
    customer_group_id: uuid.UUID | None = None
    sales_partner_id: uuid.UUID | None = None


class QuotationItemResponse(OrderItemResponse):
    pass


class QuotationResponse(OrderResponseBase):
    customer_id: uuid.UUID
    customer_name: str | None = None
    valid_till: date | None
    order_type: str
    terms: str | None = None
    customer_address_id: uuid.UUID | None = None
    shipping_address_id: uuid.UUID | None = None
    contact_person_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    territory_id: uuid.UUID | None = None
    customer_group_id: uuid.UUID | None = None
    sales_partner_id: uuid.UUID | None = None
    items: list[QuotationItemResponse]
    taxes: list[InvoiceTaxResponse]


# --- sales order -----------------------------------------------------------------------


class SalesOrderCreate(OrderCreateBase):
    customer_id: uuid.UUID
    delivery_date: date | None = None
    order_type: OrderType = "Sales"
    po_no: str | None = None
    po_date: date | None = None
    terms: str | None = None
    customer_address_id: uuid.UUID | None = None
    shipping_address_id: uuid.UUID | None = None
    contact_person_id: uuid.UUID | None = None
    set_warehouse_id: uuid.UUID | None = None
    quotation_id: uuid.UUID | None = None
    coupon_code: str | None = None
    shipping_rule_id: uuid.UUID | None = None
    # More Info (selling)
    campaign_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    territory_id: uuid.UUID | None = None
    customer_group_id: uuid.UUID | None = None
    sales_partner_id: uuid.UUID | None = None


class SalesOrderItemResponse(OrderItemResponse):
    delivery_date: date | None = None
    delivered_qty: Decimal
    billed_amt: Decimal
    quotation_item_id: uuid.UUID | None = None


class SalesOrderResponse(OrderResponseBase):
    customer_id: uuid.UUID
    customer_name: str | None = None
    delivery_date: date | None
    order_type: str
    po_no: str | None = None
    po_date: date | None = None
    terms: str | None = None
    customer_address_id: uuid.UUID | None = None
    shipping_address_id: uuid.UUID | None = None
    contact_person_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    territory_id: uuid.UUID | None = None
    customer_group_id: uuid.UUID | None = None
    sales_partner_id: uuid.UUID | None = None
    set_warehouse_id: uuid.UUID | None
    quotation_id: uuid.UUID | None
    per_delivered: Decimal
    per_billed: Decimal
    items: list[SalesOrderItemResponse]
    taxes: list[InvoiceTaxResponse]
    # transient: filled by the submit endpoint (credit-limit check, Module 05 rule 3)
    warnings: list[str] = Field(default_factory=list)
