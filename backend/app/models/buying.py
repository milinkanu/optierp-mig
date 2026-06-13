"""Module 04 (Buying) models.

Supplier (from Module 02) plus the procurement chain:
Material Request (Module 03) -> RFQ -> Supplier Quotation -> Purchase Order
-> Purchase Receipt (Module 03) -> Purchase Invoice (Module 02).

Assumptions: Supplier Group is deferred (suppliers carry a free-text type);
RFQ/Supplier Quotation are lean (no per-supplier email workflow).
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.accounts import InvoiceItemMixin, TaxRowMixin, TotalsMixin, VoucherMixin
from app.models.base import Base, CompanyScopedMixin, DocumentMixin

PO_STATUSES = (
    "Draft", "To Receive and Bill", "To Receive", "To Bill", "Completed", "Cancelled", "Closed",
)


class Supplier(Base, DocumentMixin, CompanyScopedMixin):
    """Source: erpnext/buying/doctype/supplier (stub for Module 02)."""

    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("company_id", "supplier_name", name="uq_supplier_name"),)

    supplier_name: Mapped[str] = mapped_column(String(140), nullable=False)
    supplier_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="Company", server_default=text("'Company'")
    )
    tax_id: Mapped[str | None] = mapped_column(String(80))
    default_currency: Mapped[str | None] = mapped_column(String(3))
    # Overrides the company default payable account when set
    payable_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id")
    )
    payment_terms_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_terms_templates.id", use_alter=True, name="fk_supplier_ptt")
    )
    tax_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tax_categories.id", use_alter=True, name="fk_supplier_tax_category")
    )
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    notes: Mapped[str | None] = mapped_column(Text)


class RequestForQuotation(Base, DocumentMixin, CompanyScopedMixin, VoucherMixin):
    """Source: erpnext/buying/doctype/request_for_quotation."""

    __tablename__ = "requests_for_quotation"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_rfq_name"),
        Index("ix_requests_for_quotation_company_docstatus", "company_id", "docstatus"),
    )

    schedule_date: Mapped[date | None] = mapped_column(Date)
    message_for_supplier: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Draft", server_default=text("'Draft'")
    )  # Draft | Submitted | Cancelled

    items: Mapped[list["RequestForQuotationItem"]] = relationship(
        back_populates="rfq", cascade="all, delete-orphan", order_by="RequestForQuotationItem.idx"
    )
    suppliers: Mapped[list["RequestForQuotationSupplier"]] = relationship(
        back_populates="rfq", cascade="all, delete-orphan", order_by="RequestForQuotationSupplier.idx"
    )


class RequestForQuotationItem(Base, DocumentMixin):
    __tablename__ = "request_for_quotation_items"

    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("requests_for_quotation.id", ondelete="CASCADE"), nullable=False
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("items.id"), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(21, 6), nullable=False)
    uom: Mapped[str | None] = mapped_column(String(140))
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouses.id"))
    schedule_date: Mapped[date | None] = mapped_column(Date)

    rfq: Mapped[RequestForQuotation] = relationship(back_populates="items")
    item = relationship("Item", lazy="joined", viewonly=True)

    @property
    def item_code(self) -> str | None:
        return self.item.item_code if self.item else None

    @property
    def item_name(self) -> str | None:
        return self.item.item_name if self.item else None


class RequestForQuotationSupplier(Base, DocumentMixin):
    __tablename__ = "request_for_quotation_suppliers"

    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("requests_for_quotation.id", ondelete="CASCADE"), nullable=False
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False
    )
    quote_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Pending", server_default=text("'Pending'")
    )  # Pending | Received

    rfq: Mapped[RequestForQuotation] = relationship(back_populates="suppliers")
    supplier = relationship("Supplier", lazy="joined", viewonly=True)

    @property
    def supplier_name(self) -> str | None:
        return self.supplier.supplier_name if self.supplier else None


class SupplierQuotation(Base, DocumentMixin, CompanyScopedMixin, VoucherMixin, TotalsMixin):
    """Source: erpnext/buying/doctype/supplier_quotation (lean: no tax rows;
    the Purchase Order created from it applies the tax template)."""

    __tablename__ = "supplier_quotations"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_supplier_quotation_name"),
        Index("ix_supplier_quotations_company_docstatus", "company_id", "docstatus"),
    )

    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False
    )
    rfq_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("requests_for_quotation.id")
    )
    valid_till: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Draft", server_default=text("'Draft'")
    )  # Draft | Submitted | Ordered | Cancelled

    items: Mapped[list["SupplierQuotationItem"]] = relationship(
        back_populates="quotation", cascade="all, delete-orphan", order_by="SupplierQuotationItem.idx"
    )
    supplier = relationship("Supplier", lazy="joined", viewonly=True)

    @property
    def supplier_name(self) -> str | None:
        return self.supplier.supplier_name if self.supplier else None


class SupplierQuotationItem(Base, DocumentMixin, InvoiceItemMixin):
    __tablename__ = "supplier_quotation_items"

    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("supplier_quotations.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("items.id"))
    rfq_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("request_for_quotation_items.id")
    )

    quotation: Mapped[SupplierQuotation] = relationship(back_populates="items")


class PurchaseOrder(Base, DocumentMixin, CompanyScopedMixin, VoucherMixin, TotalsMixin):
    """Source: erpnext/buying/doctype/purchase_order.

    On submit: bin.ordered_qty += pending qty per stock item; status tracking
    via per_received / per_billed (erpnext update_status / status_updater).
    """

    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_purchase_order_name"),
        Index("ix_purchase_orders_company_docstatus", "company_id", "docstatus"),
        Index("ix_purchase_orders_supplier", "supplier_id"),
    )

    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False
    )
    schedule_date: Mapped[date | None] = mapped_column(Date)  # expected receipt date
    set_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id")
    )
    supplier_quotation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("supplier_quotations.id")
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Draft", server_default=text("'Draft'")
    )
    per_received: Mapped[Decimal] = mapped_column(
        Numeric(8, 3), nullable=False, default=0, server_default=text("0")
    )
    per_billed: Mapped[Decimal] = mapped_column(
        Numeric(8, 3), nullable=False, default=0, server_default=text("0")
    )

    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="PurchaseOrderItem.idx"
    )
    taxes: Mapped[list["PurchaseOrderTax"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="PurchaseOrderTax.idx"
    )
    supplier = relationship("Supplier", lazy="joined", viewonly=True)

    @property
    def supplier_name(self) -> str | None:
        return self.supplier.supplier_name if self.supplier else None


class PurchaseOrderItem(Base, DocumentMixin, InvoiceItemMixin):
    __tablename__ = "purchase_order_items"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("items.id"))
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouses.id"))
    schedule_date: Mapped[date | None] = mapped_column(Date)
    received_qty: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    billed_amt: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    material_request_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("material_request_items.id")
    )

    order: Mapped[PurchaseOrder] = relationship(back_populates="items")


class PurchaseOrderTax(Base, DocumentMixin, TaxRowMixin):
    __tablename__ = "purchase_order_taxes"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False
    )
    add_deduct_tax: Mapped[str] = mapped_column(
        String(10), nullable=False, default="Add", server_default=text("'Add'")
    )
    category: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Total", server_default=text("'Total'")
    )

    order: Mapped[PurchaseOrder] = relationship(back_populates="taxes")
