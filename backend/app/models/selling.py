"""Module 05 (Selling) models.

Customer (from Module 02) plus the sales chain:
Quotation -> Sales Order -> Delivery Note (Module 03) -> Sales Invoice
(Module 02).

Assumptions: Customer Group / Territory / Sales Person trees and the pricing
rule engine are deferred (Item Price covers rate defaults); quotations are to
Customers only (Lead quotations arrive with CRM, Module 06).
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.accounts import InvoiceItemMixin, TaxRowMixin, TotalsMixin, VoucherMixin
from app.models.base import Base, CompanyScopedMixin, DocumentMixin

SO_STATUSES = (
    "Draft", "To Deliver and Bill", "To Deliver", "To Bill", "Completed", "Cancelled", "Closed",
)


class Customer(Base, DocumentMixin, CompanyScopedMixin):
    """Source: erpnext/selling/doctype/customer (stub for Module 02)."""

    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("company_id", "customer_name", name="uq_customer_name"),)

    customer_name: Mapped[str] = mapped_column(String(140), nullable=False)
    customer_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="Company", server_default=text("'Company'")
    )  # Company | Individual
    tax_id: Mapped[str | None] = mapped_column(String(80))
    default_currency: Mapped[str | None] = mapped_column(String(3))
    # Overrides the company default receivable account when set
    receivable_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id")
    )
    credit_limit: Mapped[float | None] = mapped_column(Numeric(21, 6))
    payment_terms_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_terms_templates.id", use_alter=True, name="fk_customer_ptt")
    )
    tax_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tax_categories.id", use_alter=True, name="fk_customer_tax_category")
    )
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    notes: Mapped[str | None] = mapped_column(Text)


class Quotation(Base, DocumentMixin, CompanyScopedMixin, VoucherMixin, TotalsMixin):
    """Source: erpnext/selling/doctype/quotation."""

    __tablename__ = "quotations"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_quotation_name"),
        Index("ix_quotations_company_docstatus", "company_id", "docstatus"),
        Index("ix_quotations_customer", "customer_id"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    valid_till: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Draft", server_default=text("'Draft'")
    )  # Draft | Open | Ordered | Cancelled | Expired

    items: Mapped[list["QuotationItem"]] = relationship(
        back_populates="quotation", cascade="all, delete-orphan", order_by="QuotationItem.idx"
    )
    taxes: Mapped[list["QuotationTax"]] = relationship(
        back_populates="quotation", cascade="all, delete-orphan", order_by="QuotationTax.idx"
    )
    customer = relationship("Customer", lazy="joined", viewonly=True)

    @property
    def customer_name(self) -> str | None:
        return self.customer.customer_name if self.customer else None


class QuotationItem(Base, DocumentMixin, InvoiceItemMixin):
    __tablename__ = "quotation_items"

    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", use_alter=True, name="fk_qi_item")
    )

    quotation: Mapped[Quotation] = relationship(back_populates="items")


class QuotationTax(Base, DocumentMixin, TaxRowMixin):
    __tablename__ = "quotation_taxes"

    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False
    )

    quotation: Mapped[Quotation] = relationship(back_populates="taxes")


class SalesOrder(Base, DocumentMixin, CompanyScopedMixin, VoucherMixin, TotalsMixin):
    """Source: erpnext/selling/doctype/sales_order.

    On submit: bin.reserved_qty += pending qty per stock item; credit-limit
    check returns a warning (not a hard block — Section 3, Module 05 rule 3).
    """

    __tablename__ = "sales_orders"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_sales_order_name"),
        Index("ix_sales_orders_company_docstatus", "company_id", "docstatus"),
        Index("ix_sales_orders_customer", "customer_id"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    delivery_date: Mapped[date | None] = mapped_column(Date)
    set_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", use_alter=True, name="fk_so_warehouse")
    )
    quotation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id")
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Draft", server_default=text("'Draft'")
    )
    per_delivered: Mapped[Decimal] = mapped_column(
        Numeric(8, 3), nullable=False, default=0, server_default=text("0")
    )
    per_billed: Mapped[Decimal] = mapped_column(
        Numeric(8, 3), nullable=False, default=0, server_default=text("0")
    )

    items: Mapped[list["SalesOrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="SalesOrderItem.idx"
    )
    taxes: Mapped[list["SalesOrderTax"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="SalesOrderTax.idx"
    )
    customer = relationship("Customer", lazy="joined", viewonly=True)

    @property
    def customer_name(self) -> str | None:
        return self.customer.customer_name if self.customer else None


class SalesOrderItem(Base, DocumentMixin, InvoiceItemMixin):
    __tablename__ = "sales_order_items"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", use_alter=True, name="fk_soi_item")
    )
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", use_alter=True, name="fk_soi_warehouse")
    )
    delivery_date: Mapped[date | None] = mapped_column(Date)
    delivered_qty: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    billed_amt: Mapped[Decimal] = mapped_column(
        Numeric(21, 6), nullable=False, default=0, server_default=text("0")
    )
    quotation_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotation_items.id")
    )

    order: Mapped[SalesOrder] = relationship(back_populates="items")


class SalesOrderTax(Base, DocumentMixin, TaxRowMixin):
    __tablename__ = "sales_order_taxes"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False
    )

    order: Mapped[SalesOrder] = relationship(back_populates="taxes")
