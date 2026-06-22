"""General Ledger service — the only writer of gl_entries.

Mirrors erpnext/accounts/general_ledger.py:
  * service-level debit == credit validation (the deferred DB trigger
    re-checks at commit, so raw SQL can never sneak an unbalanced voucher in)
  * account validation: must exist, belong to the company, be a leaf,
    not frozen/disabled
  * frozen-period check (accounts_frozen_upto system setting, maintained by
    the Period Closing Voucher)
  * budget validation for expense postings (Stop/Warn/Ignore)
  * cancellation = reversing entries (ledger stays INSERT-only)
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.accounts import Account, Budget, BudgetAccount, FiscalYear, GLEntry
from app.models.core import SystemSetting

logger = get_logger(__name__)

ZERO = Decimal("0")
FROZEN_UPTO_KEY = "accounts_frozen_upto"


@dataclass
class GLRow:
    account_id: uuid.UUID
    debit: Decimal = ZERO
    credit: Decimal = ZERO
    party_type: str | None = None
    party_id: uuid.UUID | None = None
    cost_center_id: uuid.UUID | None = None
    against: str | None = None
    against_voucher_type: str | None = None
    against_voucher_id: uuid.UUID | None = None
    account_currency: str | None = None
    debit_in_account_currency: Decimal | None = None
    credit_in_account_currency: Decimal | None = None
    remarks: str | None = None
    _account: Account = field(init=False, repr=False, default=None)  # type: ignore[assignment]


async def get_fiscal_year(db: AsyncSession, company_id: uuid.UUID, posting_date: date) -> FiscalYear:
    fy = await db.scalar(
        select(FiscalYear).where(
            FiscalYear.company_id == company_id,
            FiscalYear.year_start_date <= posting_date,
            FiscalYear.year_end_date >= posting_date,
        )
    )
    if fy is None:
        raise ValidationError(
            f"No fiscal year covers posting date {posting_date}", field="posting_date"
        )
    if fy.is_closed:
        raise ValidationError(f"Fiscal year {fy.year} is closed", field="posting_date")
    return fy


async def get_frozen_upto(db: AsyncSession, company_id: uuid.UUID) -> date | None:
    setting = await db.scalar(
        select(SystemSetting).where(
            SystemSetting.key == FROZEN_UPTO_KEY, SystemSetting.company_id == company_id
        )
    )
    if setting and setting.value:
        return date.fromisoformat(str(setting.value))
    return None


async def set_frozen_upto(db: AsyncSession, company_id: uuid.UUID, frozen_date: date) -> None:
    setting = await db.scalar(
        select(SystemSetting).where(
            SystemSetting.key == FROZEN_UPTO_KEY, SystemSetting.company_id == company_id
        )
    )
    if setting is None:
        setting = SystemSetting(key=FROZEN_UPTO_KEY, company_id=company_id)
        db.add(setting)
    setting.value = frozen_date.isoformat()


async def _validate_accounts(db: AsyncSession, company_id: uuid.UUID, rows: list[GLRow]) -> None:
    account_ids = {row.account_id for row in rows}
    accounts = {
        a.id: a
        for a in (
            await db.execute(select(Account).where(Account.id.in_(account_ids)))
        ).scalars()
    }
    for row in rows:
        account = accounts.get(row.account_id)
        if account is None:
            raise NotFoundError(f"Account {row.account_id} not found")
        if account.company_id != company_id:
            raise ValidationError(f"Account '{account.account_name}' belongs to another company")
        if account.is_group:
            raise ValidationError(
                f"Account '{account.account_name}' is a group; post to a leaf account"
            )
        if account.freeze_account or account.disabled:
            raise ValidationError(f"Account '{account.account_name}' is frozen or disabled")
        row._account = account


async def _account_spend(
    db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID, from_date: date, to_date: date
) -> Decimal:
    """Net expense (debit - credit) posted to an account in a date window."""
    total = (
        await db.execute(
            select(func.coalesce(func.sum(GLEntry.debit - GLEntry.credit), 0)).where(
                GLEntry.company_id == company_id,
                GLEntry.account_id == account_id,
                GLEntry.posting_date >= from_date,
                GLEntry.posting_date <= to_date,
            )
        )
    ).scalar_one()
    return Decimal(total)


def _cumulative_distribution_pct(md, fy: FiscalYear, posting_date: date) -> Decimal:
    """Sum of the monthly-distribution percentages from the fiscal-year start up
    to (and including) the posting month. month_1 = first month of the FY."""
    index = (
        (posting_date.year - fy.year_start_date.year) * 12
        + (posting_date.month - fy.year_start_date.month)
        + 1
    )
    index = max(1, min(index, 12))
    return sum((Decimal(getattr(md, f"month_{i}")) for i in range(1, index + 1)), ZERO)


async def _validate_budget(
    db: AsyncSession, company_id: uuid.UUID, fy: FiscalYear, rows: list[GLRow], posting_date: date
) -> None:
    """Budget check (erpnext budget_controller): always the annual cap, plus an
    optional month-to-date cap when the budget carries a Monthly Distribution."""
    from app.models.selling import MonthlyDistribution

    expense_rows = [r for r in rows if r._account.root_type == "Expense" and r.debit > r.credit]
    for row in expense_rows:
        stmt = (
            select(Budget, BudgetAccount)
            .join(BudgetAccount, BudgetAccount.budget_id == Budget.id)
            .where(
                Budget.company_id == company_id,
                Budget.fiscal_year_id == fy.id,
                Budget.docstatus == 1,
                BudgetAccount.account_id == row.account_id,
            )
        )
        if row.cost_center_id is not None:
            stmt = stmt.where(
                (Budget.cost_center_id == row.cost_center_id) | (Budget.cost_center_id.is_(None))
            )
        found = (await db.execute(stmt.limit(1))).first()
        if not found:
            continue
        budget, budget_account = found
        delta = row.debit - row.credit

        # --- annual cap ---
        if budget.action_if_annual_budget_exceeded != "Ignore":
            actual = await _account_spend(
                db, company_id, row.account_id, fy.year_start_date, fy.year_end_date
            )
            projected = actual + delta
            if projected > budget_account.budget_amount:
                message = (
                    f"Annual budget {budget_account.budget_amount} exceeded for account "
                    f"'{row._account.account_name}' (projected {projected})"
                )
                if budget.action_if_annual_budget_exceeded == "Stop":
                    raise ValidationError(message, field="account_id")
                logger.warning("budget_exceeded", detail=message)

        # --- month-to-date cap (only if a Monthly Distribution is attached) ---
        if (
            budget.monthly_distribution_id is not None
            and budget.action_if_accumulated_monthly_budget_exceeded != "Ignore"
        ):
            md = await db.get(MonthlyDistribution, budget.monthly_distribution_id)
            cum_pct = _cumulative_distribution_pct(md, fy, posting_date) if md else ZERO
            if cum_pct > ZERO:
                monthly_cap = budget_account.budget_amount * cum_pct / Decimal("100")
                spend_to_date = await _account_spend(
                    db, company_id, row.account_id, fy.year_start_date, posting_date
                )
                projected_mtd = spend_to_date + delta
                if projected_mtd > monthly_cap:
                    message = (
                        f"Month-to-date budget {monthly_cap:.2f} ({cum_pct}% of annual) exceeded "
                        f"for account '{row._account.account_name}' (projected {projected_mtd})"
                    )
                    if budget.action_if_accumulated_monthly_budget_exceeded == "Stop":
                        raise ValidationError(message, field="account_id")
                    logger.warning("monthly_budget_exceeded", detail=message)


async def make_gl_entries(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    voucher_type: str,
    voucher_id: uuid.UUID,
    voucher_no: str,
    posting_date: date,
    rows: list[GLRow],
    user_id: uuid.UUID | None = None,
    is_opening: bool = False,
    remarks: str | None = None,
) -> list[GLEntry]:
    if not rows:
        raise ValidationError("No GL rows to post")

    frozen_upto = await get_frozen_upto(db, company_id)
    if frozen_upto and posting_date <= frozen_upto:
        raise ValidationError(
            f"Posting date {posting_date} is in a frozen period (frozen upto {frozen_upto})",
            field="posting_date",
        )

    fy = await get_fiscal_year(db, company_id, posting_date)
    await _validate_accounts(db, company_id, rows)

    total_debit = sum((row.debit for row in rows), ZERO)
    total_credit = sum((row.credit for row in rows), ZERO)
    if abs(total_debit - total_credit) > Decimal("0.005"):
        raise ValidationError(
            f"Voucher is out of balance: debit {total_debit} != credit {total_credit}"
        )

    await _validate_budget(db, company_id, fy, rows, posting_date)

    entries: list[GLEntry] = []
    for row in rows:
        if row.debit < ZERO or row.credit < ZERO:
            # normalise negatives to the opposite side (ERPNext convention)
            if row.debit < ZERO:
                row.credit += -row.debit
                row.debit = ZERO
            if row.credit < ZERO:
                row.debit += -row.credit
                row.credit = ZERO
        entry = GLEntry(
            company_id=company_id,
            posting_date=posting_date,
            account_id=row.account_id,
            party_type=row.party_type,
            party_id=row.party_id,
            cost_center_id=row.cost_center_id,
            debit=row.debit,
            credit=row.credit,
            account_currency=row.account_currency or row._account.account_currency,
            debit_in_account_currency=(
                row.debit_in_account_currency if row.debit_in_account_currency is not None else row.debit
            ),
            credit_in_account_currency=(
                row.credit_in_account_currency
                if row.credit_in_account_currency is not None
                else row.credit
            ),
            voucher_type=voucher_type,
            voucher_id=voucher_id,
            voucher_no=voucher_no,
            against=row.against,
            against_voucher_type=row.against_voucher_type,
            against_voucher_id=row.against_voucher_id,
            fiscal_year_id=fy.id,
            is_opening=is_opening,
            remarks=row.remarks or remarks,
            owner=user_id,
        )
        db.add(entry)
        entries.append(entry)
    await db.flush()
    return entries


async def make_reverse_gl_entries(
    db: AsyncSession,
    *,
    voucher_type: str,
    voucher_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> int:
    """Cancel a voucher by writing mirror-image entries (debit <-> credit).

    Blocked when the original posting date falls in a frozen period or a
    closed fiscal year — otherwise cancellation would silently rewrite
    finalised books (ERPNext blocks this the same way).
    """
    originals = (
        (
            await db.execute(
                select(GLEntry).where(
                    GLEntry.voucher_type == voucher_type,
                    GLEntry.voucher_id == voucher_id,
                    GLEntry.is_cancellation.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    if not originals:
        return 0
    company_id = originals[0].company_id
    posting_date = min(e.posting_date for e in originals)
    frozen_upto = await get_frozen_upto(db, company_id)
    if frozen_upto and posting_date <= frozen_upto:
        raise ValidationError(
            f"Cannot cancel: posting date {posting_date} is in a frozen period "
            f"(frozen upto {frozen_upto})"
        )
    await get_fiscal_year(db, company_id, posting_date)  # raises if closed/missing
    for entry in originals:
        db.add(
            GLEntry(
                company_id=entry.company_id,
                posting_date=entry.posting_date,
                account_id=entry.account_id,
                party_type=entry.party_type,
                party_id=entry.party_id,
                cost_center_id=entry.cost_center_id,
                debit=entry.credit,
                credit=entry.debit,
                account_currency=entry.account_currency,
                debit_in_account_currency=entry.credit_in_account_currency,
                credit_in_account_currency=entry.debit_in_account_currency,
                voucher_type=entry.voucher_type,
                voucher_id=entry.voucher_id,
                voucher_no=entry.voucher_no,
                against=entry.against,
                against_voucher_type=entry.against_voucher_type,
                against_voucher_id=entry.against_voucher_id,
                fiscal_year_id=entry.fiscal_year_id,
                is_opening=entry.is_opening,
                is_cancellation=True,
                remarks=f"Cancellation of {entry.voucher_no}",
                owner=user_id,
            )
        )
    await db.flush()
    return len(originals)


async def get_account_balance(
    db: AsyncSession,
    account_id: uuid.UUID,
    *,
    as_of: date | None = None,
) -> Decimal:
    """Debit-minus-credit balance (positive = debit balance)."""
    stmt = select(func.coalesce(func.sum(GLEntry.debit - GLEntry.credit), 0)).where(
        GLEntry.account_id == account_id
    )
    if as_of is not None:
        stmt = stmt.where(GLEntry.posting_date <= as_of)
    return Decimal((await db.execute(stmt)).scalar_one())
