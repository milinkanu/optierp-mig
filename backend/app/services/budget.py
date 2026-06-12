"""Budget service — Module 02.

Source: erpnext/accounts/doctype/budget. A submitted (docstatus=1) budget is
enforced by app.services.gl._validate_budget on every expense posting:
Stop blocks the GL entry, Warn logs, Ignore skips. Cancelling the budget
lifts enforcement; the document itself never posts GL.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import DuplicateError, NotFoundError, ValidationError
from app.core.security import CurrentUser
from app.models.accounts import Account, Budget, BudgetAccount, CostCenter, FiscalYear
from app.models.base import DOCSTATUS_CANCELLED, DOCSTATUS_SUBMITTED
from app.schemas.accounts import BudgetCreate
from app.services.accounts_common import require_draft, require_submitted
from app.services.audit import log_audit
from app.services.pagination import paginate


async def create_budget(db: AsyncSession, payload: BudgetCreate, user: CurrentUser) -> Budget:
    if user.company_id is None:
        raise ValidationError("An active company is required")

    fiscal_year = await db.get(FiscalYear, payload.fiscal_year_id)
    if fiscal_year is None or fiscal_year.company_id != user.company_id:
        raise NotFoundError("Fiscal year not found")

    if payload.cost_center_id is not None:
        cost_center = await db.get(CostCenter, payload.cost_center_id)
        if cost_center is None or cost_center.company_id != user.company_id:
            raise NotFoundError("Cost center not found")

    if await db.scalar(
        select(Budget).where(
            Budget.company_id == user.company_id,
            Budget.fiscal_year_id == payload.fiscal_year_id,
            Budget.cost_center_id == payload.cost_center_id,
            Budget.docstatus < DOCSTATUS_CANCELLED,
        )
    ):
        raise DuplicateError(
            "A budget already exists for this fiscal year and cost center",
            field="fiscal_year_id",
        )

    seen: set[uuid.UUID] = set()
    for row in payload.accounts:
        if row.account_id in seen:
            raise ValidationError("Duplicate account in budget rows", field="accounts")
        seen.add(row.account_id)
        account = await db.get(Account, row.account_id)
        if account is None or account.company_id != user.company_id:
            raise NotFoundError("Budget account not found")
        if account.is_group:
            raise ValidationError(
                f"Budget cannot be assigned against group account {account.account_name}",
                field="accounts",
            )
        if account.root_type not in ("Income", "Expense"):
            raise ValidationError(
                f"Budget cannot be assigned against {account.account_name}: "
                "not an Income or Expense account",
                field="accounts",
            )

    budget = Budget(
        id=uuid.uuid4(),
        company_id=user.company_id,
        fiscal_year_id=payload.fiscal_year_id,
        cost_center_id=payload.cost_center_id,
        action_if_annual_budget_exceeded=payload.action_if_annual_budget_exceeded,
        owner=user.id,
        modified_by=user.id,
    )
    db.add(budget)
    await db.flush()
    for row in payload.accounts:
        db.add(
            BudgetAccount(
                budget_id=budget.id, account_id=row.account_id, budget_amount=row.budget_amount
            )
        )
    await db.flush()
    await log_audit(
        db, doctype="Budget", document_id=budget.id, action="INSERT",
        user_id=user.id, company_id=user.company_id,
    )
    await db.commit()
    return await get_budget(db, budget.id, user.company_id)


async def get_budget(
    db: AsyncSession, budget_id: uuid.UUID, company_id: uuid.UUID | None
) -> Budget:
    budget = await db.scalar(
        select(Budget)
        .options(selectinload(Budget.accounts))
        .where(Budget.id == budget_id, Budget.company_id == company_id)
    )
    if budget is None:
        raise NotFoundError("Budget not found")
    return budget


async def list_budgets(
    db: AsyncSession,
    company_id: uuid.UUID | None,
    page: int = 1,
    page_size: int = 20,
    fiscal_year_id: uuid.UUID | None = None,
) -> tuple[list[Budget], int]:
    stmt = (
        select(Budget)
        .options(selectinload(Budget.accounts))
        .where(Budget.company_id == company_id)
        .order_by(Budget.creation.desc())
    )
    if fiscal_year_id is not None:
        stmt = stmt.where(Budget.fiscal_year_id == fiscal_year_id)
    return await paginate(db, stmt, page, page_size)


async def submit_budget(db: AsyncSession, budget_id: uuid.UUID, user: CurrentUser) -> Budget:
    budget = await get_budget(db, budget_id, user.company_id)
    require_draft(budget.docstatus)
    budget.docstatus = DOCSTATUS_SUBMITTED
    budget.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Budget", document_id=budget.id, action="SUBMIT",
        user_id=user.id, company_id=budget.company_id,
    )
    await db.commit()
    return await get_budget(db, budget.id, user.company_id)


async def cancel_budget(db: AsyncSession, budget_id: uuid.UUID, user: CurrentUser) -> Budget:
    budget = await get_budget(db, budget_id, user.company_id)
    require_submitted(budget.docstatus)
    budget.docstatus = DOCSTATUS_CANCELLED
    budget.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Budget", document_id=budget.id, action="CANCEL",
        user_id=user.id, company_id=budget.company_id,
    )
    await db.commit()
    return await get_budget(db, budget.id, user.company_id)
