"""Module 03 — Stock Pydantic schemas."""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import DocumentMeta, ORMModel

# --- masters ------------------------------------------------------------------------


class ItemGroupCreate(BaseModel):
    item_group_name: str = Field(min_length=1, max_length=140)
    parent_item_group_id: uuid.UUID | None = None
    is_group: bool = False


class ItemGroupResponse(DocumentMeta):
    item_group_name: str
    parent_item_group_id: uuid.UUID | None
    is_group: bool
    disabled: bool
    company_id: uuid.UUID


class WarehouseCreate(BaseModel):
    warehouse_name: str = Field(min_length=1, max_length=140)
    parent_warehouse_id: uuid.UUID | None = None
    is_group: bool = False
    warehouse_type: str | None = None
    account_id: uuid.UUID | None = None


class WarehouseResponse(DocumentMeta):
    warehouse_name: str
    parent_warehouse_id: uuid.UUID | None
    is_group: bool
    warehouse_type: str | None
    account_id: uuid.UUID | None
    disabled: bool
    company_id: uuid.UUID


class ItemCreate(BaseModel):
    item_code: str = Field(min_length=1, max_length=140)
    item_name: str | None = None  # defaults to item_code
    description: str | None = None
    item_group_id: uuid.UUID | None = None
    stock_uom: str = "Nos"
    is_stock_item: bool = True
    is_sales_item: bool = True
    is_purchase_item: bool = True
    valuation_method: str = Field(default="Moving Average", pattern="^(Moving Average|FIFO)$")
    standard_rate: Decimal = Field(ge=0, default=Decimal("0"))
    valuation_rate: Decimal = Field(ge=0, default=Decimal("0"))
    income_account_id: uuid.UUID | None = None
    expense_account_id: uuid.UUID | None = None
    default_warehouse_id: uuid.UUID | None = None
    reorder_level: Decimal = Field(ge=0, default=Decimal("0"))
    reorder_qty: Decimal = Field(ge=0, default=Decimal("0"))
    lead_time_days: int = 0
    brand: str | None = None
    barcode: str | None = None


class ItemUpdate(BaseModel):
    item_name: str | None = None
    description: str | None = None
    item_group_id: uuid.UUID | None = None
    standard_rate: Decimal | None = Field(ge=0, default=None)
    income_account_id: uuid.UUID | None = None
    expense_account_id: uuid.UUID | None = None
    default_warehouse_id: uuid.UUID | None = None
    reorder_level: Decimal | None = Field(ge=0, default=None)
    reorder_qty: Decimal | None = Field(ge=0, default=None)
    lead_time_days: int | None = None
    brand: str | None = None
    barcode: str | None = None
    disabled: bool | None = None


class ItemResponse(DocumentMeta):
    item_code: str
    item_name: str
    description: str | None
    item_group_id: uuid.UUID | None
    item_group_name: str | None = None
    stock_uom: str
    is_stock_item: bool
    is_sales_item: bool
    is_purchase_item: bool
    valuation_method: str
    standard_rate: Decimal
    valuation_rate: Decimal
    last_purchase_rate: Decimal
    income_account_id: uuid.UUID | None
    expense_account_id: uuid.UUID | None
    default_warehouse_id: uuid.UUID | None
    reorder_level: Decimal
    reorder_qty: Decimal
    lead_time_days: int
    brand: str | None
    barcode: str | None
    disabled: bool
    company_id: uuid.UUID


class ItemListItem(ORMModel):
    id: uuid.UUID
    item_code: str
    item_name: str
    item_group_name: str | None = None
    stock_uom: str
    is_stock_item: bool
    standard_rate: Decimal
    disabled: bool


class PriceListCreate(BaseModel):
    price_list_name: str = Field(min_length=1, max_length=140)
    # defaults to company currency
    currency: str | None = Field(default=None, pattern="^[A-Za-z]{3}$")
    buying: bool = False
    selling: bool = False


class PriceListResponse(DocumentMeta):
    price_list_name: str
    currency: str
    buying: bool
    selling: bool
    enabled: bool
    company_id: uuid.UUID


class ItemPriceCreate(BaseModel):
    item_id: uuid.UUID
    price_list_id: uuid.UUID
    price_list_rate: Decimal = Field(ge=0)
    valid_from: date | None = None
    valid_upto: date | None = None


class ItemPriceResponse(DocumentMeta):
    item_id: uuid.UUID
    price_list_id: uuid.UUID
    price_list_rate: Decimal
    currency: str | None
    valid_from: date | None
    valid_upto: date | None
    company_id: uuid.UUID


class ItemRateResponse(BaseModel):
    """Resolved default rate for a document line (Item Price, else item master)."""

    item_id: uuid.UUID
    rate: Decimal
    source: str  # "Item Price" | "Standard Rate" | "Last Purchase Rate" | "Valuation Rate"
    uom: str
    item_name: str
    description: str | None = None


# --- stock entry ----------------------------------------------------------------------


class StockEntryItemIn(BaseModel):
    item_id: uuid.UUID
    qty: Decimal = Field(gt=0)
    basic_rate: Decimal = Field(ge=0, default=Decimal("0"))  # receipts; issues use valuation
    uom: str | None = None
    source_warehouse_id: uuid.UUID | None = None
    target_warehouse_id: uuid.UUID | None = None


class StockEntryCreate(BaseModel):
    purpose: str = Field(pattern="^(Material Receipt|Material Issue|Material Transfer)$")
    posting_date: date
    from_warehouse_id: uuid.UUID | None = None
    to_warehouse_id: uuid.UUID | None = None
    remarks: str | None = None
    items: list[StockEntryItemIn] = Field(min_length=1)


class StockEntryItemResponse(DocumentMeta):
    idx: int
    item_id: uuid.UUID
    item_code: str | None = None
    item_name: str | None = None
    source_warehouse_id: uuid.UUID | None
    target_warehouse_id: uuid.UUID | None
    qty: Decimal
    uom: str | None
    basic_rate: Decimal
    amount: Decimal


class StockEntryResponse(DocumentMeta):
    name: str
    posting_date: date
    purpose: str
    from_warehouse_id: uuid.UUID | None
    to_warehouse_id: uuid.UUID | None
    total_amount: Decimal
    remarks: str | None
    company_id: uuid.UUID
    items: list[StockEntryItemResponse]


class StockEntryListItem(ORMModel):
    id: uuid.UUID
    name: str
    posting_date: date
    purpose: str
    total_amount: Decimal
    docstatus: int


# --- material request -------------------------------------------------------------------


class MaterialRequestItemIn(BaseModel):
    item_id: uuid.UUID
    qty: Decimal = Field(gt=0)
    uom: str | None = None
    warehouse_id: uuid.UUID | None = None
    schedule_date: date | None = None


class MaterialRequestCreate(BaseModel):
    material_request_type: str = Field(
        default="Purchase", pattern="^(Purchase|Material Transfer|Material Issue)$"
    )
    posting_date: date
    schedule_date: date | None = None
    remarks: str | None = None
    items: list[MaterialRequestItemIn] = Field(min_length=1)


class MaterialRequestItemResponse(DocumentMeta):
    idx: int
    item_id: uuid.UUID
    item_code: str | None = None
    item_name: str | None = None
    warehouse_id: uuid.UUID | None
    qty: Decimal
    uom: str | None
    ordered_qty: Decimal
    schedule_date: date | None


class MaterialRequestResponse(DocumentMeta):
    name: str
    posting_date: date
    material_request_type: str
    schedule_date: date | None
    status: str
    per_ordered: Decimal
    remarks: str | None
    company_id: uuid.UUID
    items: list[MaterialRequestItemResponse]


class MaterialRequestListItem(ORMModel):
    id: uuid.UUID
    name: str
    posting_date: date
    material_request_type: str
    status: str
    per_ordered: Decimal
    docstatus: int


# --- purchase receipt ---------------------------------------------------------------------


class PurchaseReceiptItemIn(BaseModel):
    item_id: uuid.UUID
    qty: Decimal = Field(gt=0)
    rate: Decimal = Field(ge=0, default=Decimal("0"))
    uom: str | None = None
    warehouse_id: uuid.UUID | None = None  # falls back to set_warehouse / item default
    purchase_order_item_id: uuid.UUID | None = None


class PurchaseReceiptCreate(BaseModel):
    supplier_id: uuid.UUID
    posting_date: date
    currency: str | None = Field(default=None, pattern="^[A-Za-z]{3}$")
    conversion_rate: Decimal = Field(gt=0, default=Decimal("1"))
    set_warehouse_id: uuid.UUID | None = None
    remarks: str | None = None
    items: list[PurchaseReceiptItemIn] = Field(min_length=1)


class PurchaseReceiptItemResponse(DocumentMeta):
    idx: int
    item_id: uuid.UUID
    item_code: str | None = None
    item_name: str | None = None
    warehouse_id: uuid.UUID
    qty: Decimal
    uom: str | None
    rate: Decimal
    amount: Decimal
    base_amount: Decimal
    purchase_order_item_id: uuid.UUID | None
    billed_qty: Decimal


class PurchaseReceiptResponse(DocumentMeta):
    name: str
    posting_date: date
    supplier_id: uuid.UUID
    supplier_name: str | None = None
    currency: str
    conversion_rate: Decimal
    set_warehouse_id: uuid.UUID | None
    total_qty: Decimal
    grand_total: Decimal
    base_grand_total: Decimal
    status: str
    per_billed: Decimal
    remarks: str | None
    company_id: uuid.UUID
    items: list[PurchaseReceiptItemResponse]


class PurchaseReceiptListItem(ORMModel):
    id: uuid.UUID
    name: str
    posting_date: date
    supplier_name: str | None = None
    currency: str | None = None
    grand_total: Decimal
    status: str
    per_billed: Decimal
    docstatus: int


# --- delivery note --------------------------------------------------------------------------


class DeliveryNoteItemIn(BaseModel):
    item_id: uuid.UUID
    qty: Decimal = Field(gt=0)
    rate: Decimal = Field(ge=0, default=Decimal("0"))
    uom: str | None = None
    warehouse_id: uuid.UUID | None = None
    sales_order_item_id: uuid.UUID | None = None


class DeliveryNoteCreate(BaseModel):
    customer_id: uuid.UUID
    posting_date: date
    currency: str | None = Field(default=None, pattern="^[A-Za-z]{3}$")
    conversion_rate: Decimal = Field(gt=0, default=Decimal("1"))
    set_warehouse_id: uuid.UUID | None = None
    remarks: str | None = None
    items: list[DeliveryNoteItemIn] = Field(min_length=1)


class DeliveryNoteItemResponse(DocumentMeta):
    idx: int
    item_id: uuid.UUID
    item_code: str | None = None
    item_name: str | None = None
    warehouse_id: uuid.UUID
    qty: Decimal
    uom: str | None
    rate: Decimal
    amount: Decimal
    base_amount: Decimal
    sales_order_item_id: uuid.UUID | None
    billed_qty: Decimal


class DeliveryNoteResponse(DocumentMeta):
    name: str
    posting_date: date
    customer_id: uuid.UUID
    customer_name: str | None = None
    currency: str
    conversion_rate: Decimal
    set_warehouse_id: uuid.UUID | None
    total_qty: Decimal
    grand_total: Decimal
    base_grand_total: Decimal
    status: str
    per_billed: Decimal
    remarks: str | None
    company_id: uuid.UUID
    items: list[DeliveryNoteItemResponse]


class DeliveryNoteListItem(ORMModel):
    id: uuid.UUID
    name: str
    posting_date: date
    customer_name: str | None = None
    currency: str | None = None
    grand_total: Decimal
    status: str
    per_billed: Decimal
    docstatus: int


# --- reports ----------------------------------------------------------------------------------


class StockBalanceRow(BaseModel):
    item_id: uuid.UUID
    item_code: str
    item_name: str
    warehouse_id: uuid.UUID
    warehouse_name: str
    actual_qty: Decimal
    reserved_qty: Decimal
    ordered_qty: Decimal
    projected_qty: Decimal
    valuation_rate: Decimal
    stock_value: Decimal


class StockLedgerRow(BaseModel):
    posting_date: date
    item_code: str
    item_name: str
    warehouse_name: str
    voucher_type: str
    voucher_no: str
    actual_qty: Decimal
    qty_after_transaction: Decimal
    incoming_rate: Decimal
    valuation_rate: Decimal
    stock_value_difference: Decimal
