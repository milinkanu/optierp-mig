"""Budget endpoints — Module 02."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.accounts import BudgetCreate, BudgetResponse
from app.schemas.common import ListResponse
from app.services import budget as service

router = APIRouter(prefix="/budgets", tags=["accounts: budgets"])


@router.post(
    "",
    response_model=BudgetResponse,
    status_code=201,
    summary="Create a Budget (draft)",
    description="Annual budget per fiscal year and optional cost center. Example: "
    "`{'fiscal_year_id': '...', 'action_if_annual_budget_exceeded': 'Stop', "
    "'accounts': [{'account_id': '<Travel Expenses>', 'budget_amount': 50000}]}`. "
    "Enforced on expense GL postings once submitted.",
)
async def create(
    payload: BudgetCreate,
    current_user: Annotated[CurrentUser, Depends(require_permission("Budget", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> BudgetResponse:
    return BudgetResponse.model_validate(await service.create_budget(db, payload, current_user))


@router.get(
    "",
    response_model=ListResponse[BudgetResponse],
    summary="List Budgets",
    description="Paginated, newest first; filter by fiscal year.",
)
async def list_budgets(
    current_user: Annotated[CurrentUser, Depends(require_permission("Budget", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
    fiscal_year_id: uuid.UUID | None = None,
) -> ListResponse[BudgetResponse]:
    budgets, total = await service.list_budgets(
        db, current_user.company_id, page, page_size, fiscal_year_id
    )
    return ListResponse(
        items=[BudgetResponse.model_validate(b) for b in budgets],
        total=total, page=page, page_size=page_size,
    )


@router.get(
    "/{budget_id}",
    response_model=BudgetResponse,
    summary="Get a Budget",
    description="Budget header with its account rows.",
)
async def get_budget(
    budget_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Budget", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> BudgetResponse:
    return BudgetResponse.model_validate(
        await service.get_budget(db, budget_id, current_user.company_id)
    )


@router.post(
    "/{budget_id}/submit",
    response_model=BudgetResponse,
    summary="Submit a Budget",
    description="Activates enforcement: expense postings beyond a budgeted amount "
    "are stopped/warned per the configured action.",
)
async def submit(
    budget_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Budget", "submit"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> BudgetResponse:
    return BudgetResponse.model_validate(await service.submit_budget(db, budget_id, current_user))


@router.post(
    "/{budget_id}/cancel",
    response_model=BudgetResponse,
    summary="Cancel a Budget",
    description="Lifts enforcement; a new budget can then be created for the "
    "same fiscal year and cost center.",
)
async def cancel(
    budget_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Budget", "cancel"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> BudgetResponse:
    return BudgetResponse.model_validate(await service.cancel_budget(db, budget_id, current_user))
