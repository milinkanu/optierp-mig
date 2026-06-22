"""Module 02 master endpoints: accounts, customers, suppliers, fiscal years,
tax categories, tax templates."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.accounts import (
    AccountCreate,
    AccountResponse,
    AccountUpdate,
    CustomerCreate,
    CustomerResponse,
    OpeningInvoiceResult,
    OpeningInvoiceTool,
    SupplierCreate,
    SupplierResponse,
    TaxCategoryCreate,
    TaxCategoryResponse,
    TaxTemplateCreate,
    TaxTemplateResponse,
    TaxTemplateUpdate,
)
from app.schemas.common import ListResponse
from app.schemas.core import FiscalYearResponse
from app.services import accounts_masters as masters
from app.services import opening_invoice

router = APIRouter(tags=["accounts: masters"])


@router.post(
    "/accounts",
    response_model=AccountResponse,
    status_code=201,
    summary="Create an account",
    description="Adds an account under a group parent; root_type/report_type inherit "
    "from the parent. Example: `{'account_name': 'HDFC Bank', 'parent_account_id': "
    "'<Bank Accounts group id>', 'account_type': 'Bank'}`",
)
async def create_account(
    payload: AccountCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Account", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> AccountResponse:
    return AccountResponse.model_validate(await masters.create_account(db, payload, current_user))


@router.patch(
    "/accounts/{account_id}",
    response_model=AccountResponse,
    summary="Update an account",
    description="Partial update: rename (cascades the path to child accounts), account "
    "number/type/currency, and freeze/disable. Structural fields (root type, parent, "
    "is-group) are not editable here.",
)
async def update_account(
    account_id: uuid.UUID,
    payload: AccountUpdate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Account", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> AccountResponse:
    return AccountResponse.model_validate(
        await masters.update_account(db, account_id, payload, current_user)
    )


@router.post(
    "/customers",
    response_model=CustomerResponse,
    status_code=201,
    summary="Create a customer",
    description="Customer master (stub — extended by Module 05 Selling). "
    "Example: `{'customer_name': 'Globex Corp'}`",
)
async def create_customer(
    payload: CustomerCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Customer", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> CustomerResponse:
    return CustomerResponse.model_validate(await masters.create_customer(db, payload, current_user))


@router.get(
    "/customers",
    response_model=ListResponse[CustomerResponse],
    summary="List customers",
    description="Active customers of the current company.",
)
async def list_customers(
    current_user: Annotated[CurrentUser, Depends(require_permission("Customer", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ListResponse[CustomerResponse]:
    customers, total = await masters.list_customers(db, current_user.company_id, page, page_size)
    return ListResponse(
        items=[CustomerResponse.model_validate(c) for c in customers],
        total=total, page=page, page_size=page_size,
    )


@router.post(
    "/suppliers",
    response_model=SupplierResponse,
    status_code=201,
    summary="Create a supplier",
    description="Supplier master (stub — extended by Module 04 Buying). "
    "Example: `{'supplier_name': 'Initech Supplies'}`",
)
async def create_supplier(
    payload: SupplierCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Supplier", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> SupplierResponse:
    return SupplierResponse.model_validate(await masters.create_supplier(db, payload, current_user))


@router.get(
    "/suppliers",
    response_model=ListResponse[SupplierResponse],
    summary="List suppliers",
    description="Active suppliers of the current company.",
)
async def list_suppliers(
    current_user: Annotated[CurrentUser, Depends(require_permission("Supplier", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ListResponse[SupplierResponse]:
    suppliers, total = await masters.list_suppliers(db, current_user.company_id, page, page_size)
    return ListResponse(
        items=[SupplierResponse.model_validate(s) for s in suppliers],
        total=total, page=page, page_size=page_size,
    )


@router.get(
    "/fiscal-years",
    response_model=ListResponse[FiscalYearResponse],
    summary="List fiscal years",
    description="Fiscal years of the current company, newest first.",
)
async def list_fiscal_years(
    current_user: Annotated[CurrentUser, Depends(require_permission("Account", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> ListResponse[FiscalYearResponse]:
    rows = await masters.list_fiscal_years(db, current_user.company_id)
    items = [FiscalYearResponse.model_validate(r) for r in rows]
    return ListResponse(items=items, total=len(items), page=1, page_size=len(items) or 1)


@router.post(
    "/tax-categories",
    response_model=TaxCategoryResponse,
    status_code=201,
    summary="Create a tax category",
    description="Groups parties for tax template resolution (e.g. In-State, "
    "Out-of-State, Reverse Charge). Example: `{'title': 'In-State'}`",
)
async def create_tax_category(
    payload: TaxCategoryCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Tax Category", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> TaxCategoryResponse:
    return TaxCategoryResponse.model_validate(
        await masters.create_tax_category(db, payload, current_user)
    )


@router.get(
    "/tax-categories",
    response_model=list[TaxCategoryResponse],
    summary="List tax categories",
    description="Active tax categories of the current company.",
)
async def list_tax_categories(
    current_user: Annotated[CurrentUser, Depends(require_permission("Tax Category", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> list[TaxCategoryResponse]:
    categories = await masters.list_tax_categories(db, current_user.company_id)
    return [TaxCategoryResponse.model_validate(c) for c in categories]


@router.post(
    "/opening-invoices",
    response_model=OpeningInvoiceResult,
    status_code=201,
    summary="Opening Invoice Creation Tool",
    description="Bulk-create submitted opening invoices for outstanding receivables/payables "
    "at go-live. Each row posts its amount against the company's Temporary Opening account "
    "(no income/expense, no tax) and shows up in AR/AP aging. Example: "
    "`{'invoice_type': 'sales', 'posting_date': '2026-03-31', 'rows': [{'party_id': '<customer>', "
    "'outstanding_amount': 50000}]}`",
)
async def create_opening_invoices(
    payload: OpeningInvoiceTool,
    current_user: Annotated[CurrentUser, Depends(require_permission("Account", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> OpeningInvoiceResult:
    return await opening_invoice.create_opening_invoices(db, payload, current_user)


@router.post(
    "/tax-templates",
    response_model=TaxTemplateResponse,
    status_code=201,
    summary="Create a tax template",
    description="Sales or purchase Taxes & Charges template. Example: GST 18% = "
    "`{'title': 'GST 18%', 'kind': 'sales', 'details': [{'charge_type': 'On Net Total', "
    "'rate': 9, 'account_head_id': '<CGST>'}, {'charge_type': 'On Net Total', 'rate': 9, "
    "'account_head_id': '<SGST>'}]}`",
)
async def create_tax_template(
    payload: TaxTemplateCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Tax Template", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> TaxTemplateResponse:
    return TaxTemplateResponse.model_validate(
        await masters.create_tax_template(db, payload, current_user)
    )


@router.get(
    "/tax-templates",
    response_model=list[TaxTemplateResponse],
    summary="List tax templates",
    description="Templates filtered by kind (sales/purchase) for the current company.",
)
async def list_tax_templates(
    current_user: Annotated[CurrentUser, Depends(require_permission("Tax Template", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    kind: Annotated[str | None, Query(pattern="^(sales|purchase)$")] = None,
) -> list[TaxTemplateResponse]:
    templates = await masters.list_tax_templates(db, current_user.company_id, kind)
    return [TaxTemplateResponse.model_validate(t) for t in templates]


@router.patch(
    "/tax-templates/{template_id}",
    response_model=TaxTemplateResponse,
    summary="Update a tax template",
    description="Replaces the template header and rows (kind is not editable). Existing "
    "documents keep the tax rows they copied at creation, so edits only affect future use.",
)
async def update_tax_template(
    template_id: uuid.UUID,
    payload: TaxTemplateUpdate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Tax Template", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> TaxTemplateResponse:
    return TaxTemplateResponse.model_validate(
        await masters.update_tax_template(db, template_id, payload, current_user)
    )


@router.delete(
    "/tax-templates/{template_id}",
    status_code=204,
    summary="Delete a tax template",
    description="Removes the template and its rows. Safe for posted documents (they hold "
    "their own copied tax rows).",
)
async def delete_tax_template(
    template_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Tax Template", "delete"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> None:
    await masters.delete_tax_template(db, template_id, current_user)
