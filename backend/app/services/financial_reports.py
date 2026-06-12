"""Financial reports — Module 02 (Section 3, Module 02, rule 7).

Trial Balance, Balance Sheet, Profit & Loss, General Ledger, AR/AP aging,
Cash Flow. All reports aggregate the immutable gl_entries ledger; group
accounts roll up leaf balances via the ltree path prefix.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.accounts import Account, FiscalYear, GLEntry, PurchaseInvoice, SalesInvoice
from app.models.buying import Supplier
from app.models.selling import Customer
from app.schemas.accounts import (
    AgingRow,
    CashFlowRow,
    FinancialStatementRow,
    GLEntryResponse,
    TrialBalanceRow,
)

ZERO = Decimal("0")


async def _account_map(db: AsyncSession, company_id: uuid.UUID) -> dict[uuid.UUID, Account]:
    accounts = (
        (await db.execute(select(Account).where(Account.company_id == company_id))).scalars().all()
    )
    return {a.id: a for a in accounts}


async def _balances(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict[uuid.UUID, tuple[Decimal, Decimal]]:
    """(debit, credit) sums per leaf account in the window."""
    stmt: Select = select(
        GLEntry.account_id,
        func.coalesce(func.sum(GLEntry.debit), 0),
        func.coalesce(func.sum(GLEntry.credit), 0),
    ).where(GLEntry.company_id == company_id)
    if from_date:
        stmt = stmt.where(GLEntry.posting_date >= from_date)
    if to_date:
        stmt = stmt.where(GLEntry.posting_date <= to_date)
    rows = (await db.execute(stmt.group_by(GLEntry.account_id))).all()
    return {account_id: (Decimal(d), Decimal(c)) for account_id, d, c in rows}


def _rollup(
    accounts: dict[uuid.UUID, Account], leaf_values: dict[uuid.UUID, Decimal]
) -> dict[uuid.UUID, Decimal]:
    """Roll leaf balances up the tree using path prefixes."""
    totals: dict[uuid.UUID, Decimal] = {a_id: ZERO for a_id in accounts}
    by_path = {a.path: a.id for a in accounts.values()}
    for leaf_id, value in leaf_values.items():
        leaf = accounts.get(leaf_id)
        if leaf is None or value == ZERO:
            continue
        labels = leaf.path.split(".")
        for i in range(1, len(labels) + 1):
            ancestor_id = by_path.get(".".join(labels[:i]))
            if ancestor_id is not None:
                totals[ancestor_id] += value
    return totals


# --- General Ledger ----------------------------------------------------------------


async def general_ledger(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    from_date: date,
    to_date: date,
    account_id: uuid.UUID | None = None,
    party_type: str | None = None,
    party_id: uuid.UUID | None = None,
    voucher_no: str | None = None,
) -> dict:
    base = select(GLEntry).where(
        GLEntry.company_id == company_id,
        GLEntry.posting_date >= from_date,
        GLEntry.posting_date <= to_date,
    )
    opening_stmt = select(
        func.coalesce(func.sum(GLEntry.debit - GLEntry.credit), 0)
    ).where(GLEntry.company_id == company_id, GLEntry.posting_date < from_date)

    if account_id is not None:
        base = base.where(GLEntry.account_id == account_id)
        opening_stmt = opening_stmt.where(GLEntry.account_id == account_id)
    if party_type is not None:
        base = base.where(GLEntry.party_type == party_type)
        opening_stmt = opening_stmt.where(GLEntry.party_type == party_type)
    if party_id is not None:
        base = base.where(GLEntry.party_id == party_id)
        opening_stmt = opening_stmt.where(GLEntry.party_id == party_id)
    if voucher_no:
        base = base.where(GLEntry.voucher_no == voucher_no)

    entries = (
        (await db.execute(base.order_by(GLEntry.posting_date, GLEntry.creation))).scalars().all()
    )
    opening = Decimal((await db.execute(opening_stmt)).scalar_one())
    total_debit = sum((e.debit for e in entries), ZERO)
    total_credit = sum((e.credit for e in entries), ZERO)
    return {
        "opening_balance": opening,
        "entries": [GLEntryResponse.model_validate(e) for e in entries],
        "total_debit": total_debit,
        "total_credit": total_credit,
        "closing_balance": opening + total_debit - total_credit,
    }


# --- Trial Balance -----------------------------------------------------------------


async def trial_balance(
    db: AsyncSession, company_id: uuid.UUID, *, fiscal_year_id: uuid.UUID
) -> list[TrialBalanceRow]:
    fy = await db.get(FiscalYear, fiscal_year_id)
    if fy is None or fy.company_id != company_id:
        raise NotFoundError("Fiscal year not found")

    accounts = await _account_map(db, company_id)
    # opening = entries strictly before the year start
    opening = await _balances(
        db, company_id, to_date=date.fromordinal(fy.year_start_date.toordinal() - 1)
    )
    period = await _balances(db, company_id, from_date=fy.year_start_date, to_date=fy.year_end_date)

    opening_net = {a_id: d - c for a_id, (d, c) in opening.items()}
    period_debit = {a_id: d for a_id, (d, _) in period.items()}
    period_credit = {a_id: c for a_id, (_, c) in period.items()}

    rolled_opening = _rollup(accounts, opening_net)
    rolled_debit = _rollup(accounts, period_debit)
    rolled_credit = _rollup(accounts, period_credit)

    rows: list[TrialBalanceRow] = []
    for account in sorted(accounts.values(), key=lambda a: a.path):
        op = rolled_opening.get(account.id, ZERO)
        dr = rolled_debit.get(account.id, ZERO)
        cr = rolled_credit.get(account.id, ZERO)
        if op == ZERO and dr == ZERO and cr == ZERO:
            continue
        closing = op + dr - cr
        rows.append(
            TrialBalanceRow(
                account_id=account.id,
                account_name=account.account_name,
                root_type=account.root_type,
                is_group=account.is_group,
                path=account.path,
                opening_debit=op if op > ZERO else ZERO,
                opening_credit=-op if op < ZERO else ZERO,
                debit=dr,
                credit=cr,
                closing_debit=closing if closing > ZERO else ZERO,
                closing_credit=-closing if closing < ZERO else ZERO,
            )
        )
    return rows


# --- Financial statements ------------------------------------------------------------


def _statement_rows(
    accounts: dict[uuid.UUID, Account],
    rolled: dict[uuid.UUID, Decimal],
    root_types: tuple[str, ...],
    *,
    credit_positive: bool,
) -> list[FinancialStatementRow]:
    rows: list[FinancialStatementRow] = []
    for account in sorted(accounts.values(), key=lambda a: a.path):
        if account.root_type not in root_types:
            continue
        amount = rolled.get(account.id, ZERO)
        if amount == ZERO:
            continue
        if credit_positive:
            amount = -amount
        rows.append(
            FinancialStatementRow(
                account_id=account.id,
                account_name=account.account_name,
                root_type=account.root_type,
                is_group=account.is_group,
                indent=account.path.count("."),
                amount=amount,
            )
        )
    return rows


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


def _bucket(age: int, outstanding: Decimal) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    if age <= 30:
        return outstanding, ZERO, ZERO, ZERO
    if age <= 60:
        return ZERO, outstanding, ZERO, ZERO
    if age <= 90:
        return ZERO, ZERO, outstanding, ZERO
    return ZERO, ZERO, ZERO, outstanding


async def accounts_receivable(
    db: AsyncSession, company_id: uuid.UUID, *, as_of: date
) -> list[AgingRow]:
    rows = (
        await db.execute(
            select(SalesInvoice, Customer.customer_name)
            .join(Customer, Customer.id == SalesInvoice.customer_id)
            .where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.docstatus == 1,
                SalesInvoice.outstanding_amount > 0,
                SalesInvoice.posting_date <= as_of,
            )
            .order_by(Customer.customer_name, SalesInvoice.posting_date)
        )
    ).all()
    result = []
    for invoice, customer_name in rows:
        age = (as_of - (invoice.due_date or invoice.posting_date)).days
        b1, b2, b3, b4 = _bucket(max(age, 0), invoice.outstanding_amount)
        result.append(
            AgingRow(
                party_id=invoice.customer_id,
                party_name=customer_name,
                voucher_no=invoice.name,
                voucher_id=invoice.id,
                posting_date=invoice.posting_date,
                due_date=invoice.due_date,
                grand_total=invoice.base_grand_total,
                outstanding_amount=invoice.outstanding_amount,
                age_days=max(age, 0),
                bucket_0_30=b1,
                bucket_31_60=b2,
                bucket_61_90=b3,
                bucket_90_plus=b4,
            )
        )
    return result


async def accounts_payable(
    db: AsyncSession, company_id: uuid.UUID, *, as_of: date
) -> list[AgingRow]:
    rows = (
        await db.execute(
            select(PurchaseInvoice, Supplier.supplier_name)
            .join(Supplier, Supplier.id == PurchaseInvoice.supplier_id)
            .where(
                PurchaseInvoice.company_id == company_id,
                PurchaseInvoice.docstatus == 1,
                PurchaseInvoice.outstanding_amount > 0,
                PurchaseInvoice.posting_date <= as_of,
            )
            .order_by(Supplier.supplier_name, PurchaseInvoice.posting_date)
        )
    ).all()
    result = []
    for invoice, supplier_name in rows:
        age = (as_of - (invoice.due_date or invoice.posting_date)).days
        b1, b2, b3, b4 = _bucket(max(age, 0), invoice.outstanding_amount)
        result.append(
            AgingRow(
                party_id=invoice.supplier_id,
                party_name=supplier_name,
                voucher_no=invoice.name,
                voucher_id=invoice.id,
                posting_date=invoice.posting_date,
                due_date=invoice.due_date,
                grand_total=invoice.base_grand_total,
                outstanding_amount=invoice.outstanding_amount,
                age_days=max(age, 0),
                bucket_0_30=b1,
                bucket_31_60=b2,
                bucket_61_90=b3,
                bucket_90_plus=b4,
            )
        )
    return result


# --- Cash Flow ------------------------------------------------------------------------------


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
