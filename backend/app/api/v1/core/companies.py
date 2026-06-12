"""Company endpoints — Module 01."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.common import ListResponse
from app.schemas.core import (
    AccountListItem,
    CompanyCreate,
    CompanyListItem,
    CompanyResponse,
    CompanyUpdate,
)
from app.services import coa as coa_service
from app.services import company as company_service

router = APIRouter(prefix="/companies", tags=["core: companies"])


@router.post(
    "",
    response_model=CompanyResponse,
    status_code=201,
    summary="Create a company",
    description="Creates a company and seeds its Chart of Accounts from the chosen "
    "country template, a default cost center tree and the current fiscal year. "
    "Example: `{'company_name': 'Acme Ltd', 'abbr': 'ACME', 'default_currency': 'USD', "
    "'country_code': 'US'}`",
)
async def create_company(
    payload: CompanyCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Company", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> CompanyResponse:
    company = await company_service.create_company(db, payload, current_user)
    return CompanyResponse.model_validate(company)


@router.get(
    "",
    response_model=ListResponse[CompanyListItem],
    summary="List accessible companies",
    description="Returns companies the user holds a role in (all companies for System Managers).",
)
async def list_companies(
    current_user: Annotated[CurrentUser, Depends(require_permission("Company", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
) -> ListResponse[CompanyListItem]:
    companies, total = await company_service.list_companies(db, current_user, page, page_size)
    return ListResponse(
        items=[CompanyListItem.model_validate(c) for c in companies],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/meta/coa-templates",
    response_model=list[str],
    summary="List available Chart of Accounts templates",
    description="Template keys usable in CompanyCreate.chart_of_accounts_template.",
)
async def list_coa_templates(
    current_user: Annotated[CurrentUser, Depends(require_permission("Company", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> list[str]:
    return coa_service.available_templates()


@router.get(
    "/{company_id}",
    response_model=CompanyResponse,
    summary="Get a company",
    description="Full company record including resolved default accounts.",
)
async def get_company(
    company_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Company", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> CompanyResponse:
    return CompanyResponse.model_validate(await company_service.get_company(db, company_id))


@router.patch(
    "/{company_id}",
    response_model=CompanyResponse,
    summary="Update a company",
    description="Partial update of company details and default account links.",
)
async def update_company(
    company_id: uuid.UUID,
    payload: CompanyUpdate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Company", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> CompanyResponse:
    company = await company_service.update_company(db, company_id, payload, current_user)
    return CompanyResponse.model_validate(company)


@router.get(
    "/{company_id}/chart-of-accounts",
    response_model=list[AccountListItem],
    summary="Get the company's Chart of Accounts tree",
    description="Accounts ordered by materialised path; rebuild the tree client-side "
    "via parent_account_id.",
)
async def get_chart_of_accounts(
    company_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Account", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> list[AccountListItem]:
    accounts = await coa_service.get_account_tree(db, company_id)
    return [AccountListItem.model_validate(a) for a in accounts]
