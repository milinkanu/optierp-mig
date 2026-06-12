"""Module 02 masters service: accounts CRUD, customers/suppliers (stubs),
fiscal years, tax categories, tax templates."""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import DuplicateError, NotFoundError, ValidationError
from app.core.security import CurrentUser
from app.models.accounts import (
    ROOT_TYPE_REPORT,
    Account,
    FiscalYear,
    TaxCategory,
    TaxTemplate,
    TaxTemplateDetail,
)
from app.models.buying import Supplier
from app.models.selling import Customer
from app.schemas.accounts import (
    AccountCreate,
    CustomerCreate,
    SupplierCreate,
    TaxCategoryCreate,
    TaxTemplateCreate,
)
from app.services.audit import log_audit
from app.services.pagination import paginate


def _slugify(label: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", label.lower()).strip("_")
    return slug or "node"


# --- Account CRUD (tree-aware) ------------------------------------------------------


async def create_account(db: AsyncSession, payload: AccountCreate, user: CurrentUser) -> Account:
    parent = await db.get(Account, payload.parent_account_id)
    if parent is None or parent.company_id != user.company_id:
        raise NotFoundError("Parent account not found")
    if not parent.is_group:
        raise ValidationError("Parent account must be a group account", field="parent_account_id")

    duplicate = await db.scalar(
        select(Account).where(
            Account.company_id == user.company_id,
            Account.account_name == payload.account_name,
            Account.parent_account_id == parent.id,
        )
    )
    if duplicate:
        raise DuplicateError("An account with this name already exists here", field="account_name")

    account = Account(
        id=uuid.uuid4(),
        company_id=parent.company_id,
        account_name=payload.account_name,
        account_number=payload.account_number,
        parent_account_id=parent.id,
        root_type=parent.root_type,
        report_type=ROOT_TYPE_REPORT[parent.root_type],
        account_type=payload.account_type,
        is_group=payload.is_group,
        account_currency=payload.account_currency or parent.account_currency,
        path=f"{parent.path}.{_slugify(payload.account_name)}",
        owner=user.id,
    )
    db.add(account)
    await db.flush()
    await log_audit(
        db, doctype="Account", document_id=account.id, action="INSERT",
        user_id=user.id, company_id=account.company_id,
    )
    await db.commit()
    await db.refresh(account)
    return account


# --- Customers / Suppliers (stub masters for invoicing) ------------------------------


async def create_customer(db: AsyncSession, payload: CustomerCreate, user: CurrentUser) -> Customer:
    if user.company_id is None:
        raise ValidationError("An active company is required")
    if await db.scalar(
        select(Customer).where(
            Customer.company_id == user.company_id, Customer.customer_name == payload.customer_name
        )
    ):
        raise DuplicateError("Customer already exists", field="customer_name")
    customer = Customer(company_id=user.company_id, owner=user.id, **payload.model_dump())
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


async def list_customers(
    db: AsyncSession, company_id: uuid.UUID | None, page: int = 1, page_size: int = 50
) -> tuple[list[Customer], int]:
    stmt = (
        select(Customer)
        .where(Customer.company_id == company_id, Customer.disabled.is_(False))
        .order_by(Customer.customer_name)
    )
    return await paginate(db, stmt, page, page_size)


async def create_supplier(db: AsyncSession, payload: SupplierCreate, user: CurrentUser) -> Supplier:
    if user.company_id is None:
        raise ValidationError("An active company is required")
    if await db.scalar(
        select(Supplier).where(
            Supplier.company_id == user.company_id, Supplier.supplier_name == payload.supplier_name
        )
    ):
        raise DuplicateError("Supplier already exists", field="supplier_name")
    supplier = Supplier(company_id=user.company_id, owner=user.id, **payload.model_dump())
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    return supplier


async def list_suppliers(
    db: AsyncSession, company_id: uuid.UUID | None, page: int = 1, page_size: int = 50
) -> tuple[list[Supplier], int]:
    stmt = (
        select(Supplier)
        .where(Supplier.company_id == company_id, Supplier.disabled.is_(False))
        .order_by(Supplier.supplier_name)
    )
    return await paginate(db, stmt, page, page_size)


# --- Fiscal years ------------------------------------------------------------------------


async def list_fiscal_years(db: AsyncSession, company_id: uuid.UUID | None) -> list[FiscalYear]:
    if company_id is None:
        raise ValidationError("An active company is required")
    stmt = (
        select(FiscalYear)
        .where(FiscalYear.company_id == company_id)
        .order_by(FiscalYear.year_start_date.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


# --- Tax categories ------------------------------------------------------------------------


async def create_tax_category(
    db: AsyncSession, payload: TaxCategoryCreate, user: CurrentUser
) -> TaxCategory:
    if user.company_id is None:
        raise ValidationError("An active company is required")
    if await db.scalar(
        select(TaxCategory).where(
            TaxCategory.company_id == user.company_id, TaxCategory.title == payload.title
        )
    ):
        raise DuplicateError("Tax category already exists", field="title")
    category = TaxCategory(company_id=user.company_id, owner=user.id, **payload.model_dump())
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


async def list_tax_categories(
    db: AsyncSession, company_id: uuid.UUID | None
) -> list[TaxCategory]:
    stmt = (
        select(TaxCategory)
        .where(TaxCategory.company_id == company_id, TaxCategory.disabled.is_(False))
        .order_by(TaxCategory.title)
    )
    return list((await db.execute(stmt)).scalars().all())


async def resolve_tax_template(
    db: AsyncSession,
    company_id: uuid.UUID,
    kind: str,
    tax_category_id: uuid.UUID | None,
) -> TaxTemplate | None:
    """Pick the tax template for an invoice (erpnext get_party_details):
    a template tagged with the party's tax category wins; otherwise the
    company default template (untagged) applies; otherwise no taxes."""
    base = (
        select(TaxTemplate)
        .options(selectinload(TaxTemplate.details))
        .where(
            TaxTemplate.company_id == company_id,
            TaxTemplate.kind == kind,
            TaxTemplate.disabled.is_(False),
        )
    )
    if tax_category_id is not None:
        template = await db.scalar(base.where(TaxTemplate.tax_category_id == tax_category_id))
        if template is not None:
            return template
    return await db.scalar(
        base.where(TaxTemplate.is_default.is_(True), TaxTemplate.tax_category_id.is_(None))
    )


# --- Tax templates ---------------------------------------------------------------------


async def create_tax_template(
    db: AsyncSession, payload: TaxTemplateCreate, user: CurrentUser
) -> TaxTemplate:
    if user.company_id is None:
        raise ValidationError("An active company is required")
    if await db.scalar(
        select(TaxTemplate).where(
            TaxTemplate.company_id == user.company_id,
            TaxTemplate.title == payload.title,
            TaxTemplate.kind == payload.kind,
        )
    ):
        raise DuplicateError("Tax template already exists", field="title")

    if payload.tax_category_id is not None:
        category = await db.get(TaxCategory, payload.tax_category_id)
        if category is None or category.company_id != user.company_id:
            raise NotFoundError("Tax category not found")

    template = TaxTemplate(
        id=uuid.uuid4(),
        company_id=user.company_id,
        title=payload.title,
        kind=payload.kind,
        is_default=payload.is_default,
        tax_category_id=payload.tax_category_id,
        owner=user.id,
    )
    db.add(template)
    await db.flush()
    for idx, row in enumerate(payload.details, start=1):
        db.add(
            TaxTemplateDetail(
                template_id=template.id,
                idx=idx,
                charge_type=row.charge_type,
                rate=row.rate,
                tax_amount=row.tax_amount,
                row_id=row.row_id,
                account_head_id=row.account_head_id,
                cost_center_id=row.cost_center_id,
                description=row.description,
                add_deduct_tax=row.add_deduct_tax,
                category=row.category,
            )
        )
    await db.commit()
    return await get_tax_template(db, template.id, user.company_id)


async def get_tax_template(
    db: AsyncSession, template_id: uuid.UUID, company_id: uuid.UUID | None
) -> TaxTemplate:
    template = await db.scalar(
        select(TaxTemplate)
        .options(selectinload(TaxTemplate.details))
        .where(TaxTemplate.id == template_id, TaxTemplate.company_id == company_id)
    )
    if template is None:
        raise NotFoundError("Tax template not found")
    return template


async def list_tax_templates(
    db: AsyncSession, company_id: uuid.UUID | None, kind: str | None = None
) -> list[TaxTemplate]:
    stmt = (
        select(TaxTemplate)
        .options(selectinload(TaxTemplate.details))
        .where(TaxTemplate.company_id == company_id, TaxTemplate.disabled.is_(False))
        .order_by(TaxTemplate.title)
    )
    if kind:
        stmt = stmt.where(TaxTemplate.kind == kind)
    return list((await db.execute(stmt)).scalars().all())
