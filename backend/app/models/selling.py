"""Module 05 (Selling) models — partial.

Customer is stubbed here because Module 02 invoices require a receivable
party. Module 05 extends it (customer groups, territories, sales team,
credit limits) and adds quotations/sales orders.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CompanyScopedMixin, DocumentMixin


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
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    notes: Mapped[str | None] = mapped_column(Text)
