"""Reports — Gross Profit + Budget Variance."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.models.accounts import (
    Budget,
    FiscalYear,
    SalesInvoice,
)
from app.models.stock import StockLedgerEntry
from app.schemas.accounts import (
    BudgetVarianceRow,
    GrossProfitReport,
    GrossProfitRow,
)

from app.services.financial_reports._helpers import (
    ZERO, _account_map, _balances,
)

async def gross_profit(
    db: AsyncSession, company_id: uuid.UUID, *, from_date: date, to_date: date
) -> GrossProfitReport:
    """Margin per item: selling (invoice net) minus COGS, where COGS uses each
    item's latest moving-average valuation rate from the stock ledger.

    Simplification (flagged): cost is the item's *current* valuation, not the
    exact cost at the moment of each sale (which would need the delivery's stock
    ledger entry). Good enough for "which items/lines earn margin"; returns and
    opening invoices are excluded. Non-stock / service lines (no stock ledger
    entry) carry zero cost."""
    invoices = (
        (
            await db.execute(
                select(SalesInvoice)
                .options(selectinload(SalesInvoice.items))
                .where(
                    SalesInvoice.company_id == company_id,
                    SalesInvoice.docstatus == 1,
                    SalesInvoice.is_opening.is_(False),
                    SalesInvoice.is_return.is_(False),
                    SalesInvoice.posting_date >= from_date,
                    SalesInvoice.posting_date <= to_date,
                )
            )
        )
        .scalars()
        .all()
    )

    item_ids = {it.item_id for inv in invoices for it in inv.items if it.item_id is not None}
    valuation: dict[uuid.UUID, Decimal] = {}
    if item_ids:
        # DISTINCT ON (item_id) -> the most recent stock-ledger valuation per item
        rows = (
            await db.execute(
                select(StockLedgerEntry.item_id, StockLedgerEntry.valuation_rate)
                .where(
                    StockLedgerEntry.company_id == company_id,
                    StockLedgerEntry.item_id.in_(item_ids),
                )
                .distinct(StockLedgerEntry.item_id)
                .order_by(
                    StockLedgerEntry.item_id,
                    StockLedgerEntry.posting_date.desc(),
                    StockLedgerEntry.creation.desc(),
                )
            )
        ).all()
        valuation = {item_id: Decimal(rate) for item_id, rate in rows}

    agg: dict[str, dict] = {}
    for inv in invoices:
        for it in inv.items:
            key = str(it.item_id) if it.item_id else f"name:{it.item_name}"
            rate = valuation.get(it.item_id, ZERO) if it.item_id else ZERO
            cogs = (rate * it.qty).quantize(Decimal("0.01"))
            bucket = agg.setdefault(
                key,
                {"item_code": it.item_code, "item_name": it.item_name,
                 "qty": ZERO, "selling": ZERO, "cogs": ZERO},
            )
            bucket["qty"] += it.qty
            bucket["selling"] += it.net_amount
            bucket["cogs"] += cogs

    result_rows: list[GrossProfitRow] = []
    total_selling = total_cogs = ZERO
    for b in agg.values():
        gp = b["selling"] - b["cogs"]
        margin = (gp / b["selling"] * Decimal("100")).quantize(Decimal("0.01")) if b["selling"] else ZERO
        result_rows.append(
            GrossProfitRow(
                item_code=b["item_code"], item_name=b["item_name"], qty=b["qty"],
                selling=b["selling"], cogs=b["cogs"], gross_profit=gp, margin_pct=margin,
            )
        )
        total_selling += b["selling"]
        total_cogs += b["cogs"]
    result_rows.sort(key=lambda r: r.gross_profit, reverse=True)

    total_gp = total_selling - total_cogs
    total_margin = (
        (total_gp / total_selling * Decimal("100")).quantize(Decimal("0.01")) if total_selling else ZERO
    )
    return GrossProfitReport(
        rows=result_rows,
        total_selling=total_selling,
        total_cogs=total_cogs,
        total_gross_profit=total_gp,
        margin_pct=total_margin,
    )


# --- Budget Variance --------------------------------------------------------------------------


async def budget_variance(
    db: AsyncSession, company_id: uuid.UUID, *, fiscal_year_id: uuid.UUID
) -> list[BudgetVarianceRow]:
    """Per budgeted account: the budgeted amount vs the actual (GL net debit-credit)
    spent within the fiscal year. Positive variance = under budget."""
    fy = await db.get(FiscalYear, fiscal_year_id)
    if fy is None or fy.company_id != company_id:
        raise NotFoundError("Fiscal year not found")

    budgets = (
        (
            await db.execute(
                select(Budget)
                .options(selectinload(Budget.accounts))
                .where(
                    Budget.company_id == company_id,
                    Budget.fiscal_year_id == fiscal_year_id,
                    Budget.docstatus == 1,
                )
            )
        )
        .scalars()
        .all()
    )
    budget_by_account: dict[uuid.UUID, Decimal] = {}
    for b in budgets:
        for row in b.accounts:
            budget_by_account[row.account_id] = budget_by_account.get(row.account_id, ZERO) + row.budget_amount
    if not budget_by_account:
        return []

    accounts = await _account_map(db, company_id)
    actuals = await _balances(db, company_id, from_date=fy.year_start_date, to_date=fy.year_end_date)

    rows: list[BudgetVarianceRow] = []
    for account_id, budget in budget_by_account.items():
        debit, credit = actuals.get(account_id, (ZERO, ZERO))
        actual = debit - credit  # expense accounts: positive = spent
        variance = budget - actual
        pct = (variance / budget * Decimal("100")).quantize(Decimal("0.01")) if budget else ZERO
        account = accounts.get(account_id)
        rows.append(
            BudgetVarianceRow(
                account_id=account_id,
                account_name=account.account_name if account else str(account_id),
                budget=budget,
                actual=actual,
                variance=variance,
                variance_pct=pct,
            )
        )
    rows.sort(key=lambda r: r.account_name)
    return rows
