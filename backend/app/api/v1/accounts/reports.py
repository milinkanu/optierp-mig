"""Financial report endpoints — Module 02 (Section 3, Module 02, rule 7)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.accounts import AgingRow, CashFlowRow, TrialBalanceRow
from app.services import financial_reports as reports
from app.services import period_closing
from app.schemas.accounts import PeriodClosingCreate, PeriodClosingResponse

router = APIRouter(prefix="/reports", tags=["accounts: reports"])


def _company(current_user: CurrentUser) -> uuid.UUID:
    if current_user.company_id is None:
        raise ValidationError("An active company is required")
    return current_user.company_id


@router.get(
    "/general-ledger",
    summary="General Ledger",
    description="Ledger entries in a date window with opening/closing balances; "
    "filter by account, party or voucher number.",
)
async def general_ledger(
    current_user: Annotated[CurrentUser, Depends(require_permission("GL Entry", "report"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    from_date: date,
    to_date: date,
    account_id: uuid.UUID | None = None,
    party_type: str | None = None,
    party_id: uuid.UUID | None = None,
    voucher_no: str | None = None,
) -> dict:
    return await reports.general_ledger(
        db, _company(current_user),
        from_date=from_date, to_date=to_date,
        account_id=account_id, party_type=party_type, party_id=party_id, voucher_no=voucher_no,
    )


@router.get(
    "/trial-balance",
    response_model=list[TrialBalanceRow],
    summary="Trial Balance",
    description="Opening / period / closing debit-credit per account for a fiscal year, "
    "with group accounts rolled up.",
)
async def trial_balance(
    current_user: Annotated[CurrentUser, Depends(require_permission("GL Entry", "report"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    fiscal_year_id: uuid.UUID,
) -> list[TrialBalanceRow]:
    return await reports.trial_balance(db, _company(current_user), fiscal_year_id=fiscal_year_id)


@router.get(
    "/profit-loss",
    summary="Profit and Loss Statement",
    description="Income and expense balances for a period plus net profit.",
)
async def profit_loss(
    current_user: Annotated[CurrentUser, Depends(require_permission("GL Entry", "report"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    from_date: date,
    to_date: date,
) -> dict:
    return await reports.profit_and_loss(db, _company(current_user), from_date=from_date, to_date=to_date)


@router.get(
    "/balance-sheet",
    summary="Balance Sheet",
    description="Assets, liabilities and equity as of a date; includes the provisional "
    "(un-closed) profit/loss line that keeps the equation balanced.",
)
async def balance_sheet(
    current_user: Annotated[CurrentUser, Depends(require_permission("GL Entry", "report"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    as_of: date,
) -> dict:
    return await reports.balance_sheet(db, _company(current_user), as_of=as_of)


@router.get(
    "/accounts-receivable",
    response_model=list[AgingRow],
    summary="Accounts Receivable (aging)",
    description="Outstanding sales invoices per customer with 0-30/31-60/61-90/90+ buckets.",
)
async def accounts_receivable(
    current_user: Annotated[CurrentUser, Depends(require_permission("Sales Invoice", "report"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    as_of: date | None = None,
) -> list[AgingRow]:
    return await reports.accounts_receivable(db, _company(current_user), as_of=as_of or date.today())


@router.get(
    "/accounts-payable",
    response_model=list[AgingRow],
    summary="Accounts Payable (aging)",
    description="Outstanding purchase invoices per supplier with aging buckets.",
)
async def accounts_payable(
    current_user: Annotated[CurrentUser, Depends(require_permission("Purchase Invoice", "report"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    as_of: date | None = None,
) -> list[AgingRow]:
    return await reports.accounts_payable(db, _company(current_user), as_of=as_of or date.today())


@router.get(
    "/cash-flow",
    response_model=list[CashFlowRow],
    summary="Cash Flow Statement",
    description="Direct-method cash movement on Cash/Bank accounts for a period.",
)
async def cash_flow(
    current_user: Annotated[CurrentUser, Depends(require_permission("GL Entry", "report"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    from_date: date,
    to_date: date,
) -> list[CashFlowRow]:
    return await reports.cash_flow(db, _company(current_user), from_date=from_date, to_date=to_date)


@router.post(
    "/period-closing",
    response_model=PeriodClosingResponse,
    status_code=201,
    summary="Run a Period Closing Voucher",
    description="Transfers P&L balances to the closing (retained earnings) account and "
    "freezes GL postings up to the date. Atomic create + submit.",
)
async def run_period_closing(
    payload: PeriodClosingCreate,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("Period Closing Voucher", "submit"))
    ],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> PeriodClosingResponse:
    return PeriodClosingResponse.model_validate(
        await period_closing.create_and_submit_period_closing(db, payload, current_user)
    )
