"""Module 04 (Buying) models — partial.

Supplier is stubbed here because Module 02 purchase invoices require a
payable party. Module 04 extends it (supplier groups, RFQs, purchase orders).
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CompanyScopedMixin, DocumentMixin


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
