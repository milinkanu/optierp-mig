"""Reports — P&L, Balance Sheet, Cash Flow."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.accounts import (
    Account,
    GLEntry,
)
from app.schemas.accounts import (
    CashFlowRow,
)

from app.services.financial_reports._helpers import (
    ZERO, _account_map, _balances, _rollup, _statement_rows,
)

async def profit_and_loss(
    db: AsyncSession, company_id: uuid.UUID, *, from_date: date, to_date: date
) -> dict:
    accounts = await _account_map(db, company_id)
    period = await _balances(db, company_id, from_date=from_date, to_date=to_date)
    net = {a_id: d - c for a_id, (d, c) in period.items()}
    rolled = _rollup(accounts, net)

    income_rows = _statement_rows(accounts, rolled, ("Income",), credit_positive=True)
    expense_rows = _statement_rows(accounts, rolled, ("Expense",), credit_positive=False)
    total_income = sum((r.amount for r in income_rows if not r.is_group), ZERO)
    total_expense = sum((r.amount for r in expense_rows if not r.is_group), ZERO)
    return {
        "income": income_rows,
        "expenses": expense_rows,
        "total_income": total_income,
        "total_expense": total_expense,
        "net_profit": total_income - total_expense,
    }


async def balance_sheet(db: AsyncSession, company_id: uuid.UUID, *, as_of: date) -> dict:
    accounts = await _account_map(db, company_id)
    cumulative = await _balances(db, company_id, to_date=as_of)
    net = {a_id: d - c for a_id, (d, c) in cumulative.items()}
    rolled = _rollup(accounts, net)

    assets = _statement_rows(accounts, rolled, ("Asset",), credit_positive=False)
    liabilities = _statement_rows(accounts, rolled, ("Liability",), credit_positive=True)
    equity = _statement_rows(accounts, rolled, ("Equity",), credit_positive=True)

    total_assets = sum((r.amount for r in assets if not r.is_group), ZERO)
    total_liabilities = sum((r.amount for r in liabilities if not r.is_group), ZERO)
    total_equity = sum((r.amount for r in equity if not r.is_group), ZERO)
    # un-closed P&L surplus keeps the equation balanced
    provisional_profit = total_assets - total_liabilities - total_equity
    return {
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "total_equity": total_equity,
        "provisional_profit_loss": provisional_profit,
    }


# --- AR / AP aging ----------------------------------------------------------------------


async def cash_flow(
    db: AsyncSession, company_id: uuid.UUID, *, from_date: date, to_date: date
) -> list[CashFlowRow]:
    """Direct-method cash flow, simplified: movements on Cash/Bank accounts
    classified by the counterpart voucher type.

    Assumption (flagged): ERPNext's report classifies via account mapping
    (Cash Flow Mapper); voucher-type classification approximates it until
    Modules 03/10 add asset/loan flows.
    """
    if from_date > to_date:
        raise ValidationError("from_date must be before to_date")

    cash_accounts = select(Account.id).where(
        Account.company_id == company_id, Account.account_type.in_(["Cash", "Bank"])
    )
    moves = (
        await db.execute(
            select(
                GLEntry.voucher_type,
                func.coalesce(func.sum(GLEntry.debit - GLEntry.credit), 0),
            )
            .where(
                GLEntry.company_id == company_id,
                GLEntry.account_id.in_(cash_accounts),
                GLEntry.posting_date >= from_date,
                GLEntry.posting_date <= to_date,
            )
            .group_by(GLEntry.voucher_type)
        )
    ).all()

    opening = Decimal(
        (
            await db.execute(
                select(func.coalesce(func.sum(GLEntry.debit - GLEntry.credit), 0)).where(
                    GLEntry.company_id == company_id,
                    GLEntry.account_id.in_(cash_accounts),
                    GLEntry.posting_date < from_date,
                )
            )
        ).scalar_one()
    )

    rows = [CashFlowRow(section="Opening", label="Opening cash balance", amount=opening)]
    operating = ZERO
    for voucher_type, amount in moves:
        amount = Decimal(amount)
        rows.append(
            CashFlowRow(section="Operating", label=f"Net cash via {voucher_type}", amount=amount)
        )
        operating += amount
    rows.append(CashFlowRow(section="Operating", label="Net cash from operations", amount=operating))
    rows.append(
        CashFlowRow(section="Closing", label="Closing cash balance", amount=opening + operating)
    )
    return rows


# --- Bank Reconciliation Statement ------------------------------------------------------------


