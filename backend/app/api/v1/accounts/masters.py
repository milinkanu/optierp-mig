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
    CustomerCreate,
    CustomerResponse,
    SupplierCreate,
    SupplierResponse,
    TaxCategoryCreate,
    TaxCategoryResponse,
    TaxTemplateCreate,
    TaxTemplateResponse,
)
from app.schemas.common import ListResponse
from app.schemas.core import FiscalYearResponse
from app.services import accounts_masters as masters

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
