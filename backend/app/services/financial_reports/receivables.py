"""Reports — AR/AP aging + Bank Reconciliation."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.accounts import (
    Account,
    GLEntry,
    JournalEntry,
    JournalEntryAccount,
    PaymentEntry,
    PaymentEntryReference,
    PurchaseInvoice,
    SalesInvoice,
)
from app.models.buying import Supplier
from app.models.selling import Customer
from app.schemas.accounts import (
    AgingRow,
    BankReconciliationReport,
    BankReconUnclearedRow,
    CollectionSummaryRow,
    PartyOutstandingSummaryRow,
)

from app.services.financial_reports._helpers import (
    ZERO, _bucket,
)

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


# --- AR/AP summary (per-party rollup) + collection period --------------------------------


def _summarize_by_party(rows: list[AgingRow]) -> list[PartyOutstandingSummaryRow]:
    agg: dict = {}
    for r in rows:
        a = agg.get(r.party_id)
        if a is None:
            a = agg[r.party_id] = {"name": r.party_name, "out": ZERO, "b1": ZERO, "b2": ZERO, "b3": ZERO, "b4": ZERO}
        a["out"] += r.outstanding_amount
        a["b1"] += r.bucket_0_30
        a["b2"] += r.bucket_31_60
        a["b3"] += r.bucket_61_90
        a["b4"] += r.bucket_90_plus
    out = [
        PartyOutstandingSummaryRow(
            party_id=pid, party_name=a["name"], outstanding_amount=a["out"],
            bucket_0_30=a["b1"], bucket_31_60=a["b2"], bucket_61_90=a["b3"], bucket_90_plus=a["b4"],
        )
        for pid, a in agg.items()
    ]
    out.sort(key=lambda r: r.party_name)
    return out


async def accounts_receivable_summary(
    db: AsyncSession, company_id: uuid.UUID, *, as_of: date
) -> list[PartyOutstandingSummaryRow]:
    """One row per customer: total receivable rolled up across their open invoices, aged."""
    return _summarize_by_party(await accounts_receivable(db, company_id, as_of=as_of))


async def accounts_payable_summary(
    db: AsyncSession, company_id: uuid.UUID, *, as_of: date
) -> list[PartyOutstandingSummaryRow]:
    """One row per supplier: total payable rolled up across their open bills, aged."""
    return _summarize_by_party(await accounts_payable(db, company_id, as_of=as_of))


async def collection_summary(
    db: AsyncSession, company_id: uuid.UUID, *, from_date: date, to_date: date
) -> list[CollectionSummaryRow]:
    """Per-customer collection speed: for sales invoices fully paid (outstanding<=0) whose
    last payment landed in the window, the average days from invoice date to that payment."""
    paid = (
        select(
            PaymentEntryReference.reference_id.label("inv_id"),
            func.max(PaymentEntry.posting_date).label("paid_on"),
        )
        .join(PaymentEntry, PaymentEntry.id == PaymentEntryReference.payment_entry_id)
        .where(
            PaymentEntryReference.reference_doctype == "Sales Invoice",
            PaymentEntry.company_id == company_id,
            PaymentEntry.docstatus == 1,
        )
        .group_by(PaymentEntryReference.reference_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(SalesInvoice, Customer.customer_name, paid.c.paid_on)
            .join(Customer, Customer.id == SalesInvoice.customer_id)
            .join(paid, paid.c.inv_id == SalesInvoice.id)
            .where(
                SalesInvoice.company_id == company_id,
                SalesInvoice.docstatus == 1,
                SalesInvoice.outstanding_amount <= 0,
                paid.c.paid_on >= from_date,
                paid.c.paid_on <= to_date,
            )
        )
    ).all()
    agg: dict = {}
    for invoice, customer_name, paid_on in rows:
        a = agg.get(invoice.customer_id)
        if a is None:
            a = agg[invoice.customer_id] = {"name": customer_name, "count": 0, "days": 0, "collected": ZERO}
        a["count"] += 1
        a["days"] += max((paid_on - invoice.posting_date).days, 0)
        a["collected"] += invoice.base_grand_total
    out = [
        CollectionSummaryRow(
            party_id=cid, party_name=a["name"], paid_invoices=a["count"],
            avg_days_to_pay=round(a["days"] / a["count"]) if a["count"] else 0,
            total_collected=a["collected"],
        )
        for cid, a in agg.items()
    ]
    out.sort(key=lambda r: r.party_name)
    return out


# --- Cash Flow ------------------------------------------------------------------------------


async def bank_reconciliation(
    db: AsyncSession, company_id: uuid.UUID, *, gl_account_id: uuid.UUID, as_of: date
) -> BankReconciliationReport:
    """Balance per books vs. per bank for a Bank/Cash GL account.

    Uncleared = submitted Payment Entries / Journal Entry rows touching the
    account, posted on or before as_of, whose clearance_date is unset or
    after as_of. balance_per_bank = balance_per_books - net uncleared amount
    (erpnext bank_reconciliation_statement).
    """
    account = await db.get(Account, gl_account_id)
    if account is None or account.company_id != company_id:
        raise NotFoundError("Account not found")
    if account.is_group:
        raise ValidationError("Pick a leaf account, not a group", field="gl_account_id")
    if account.account_type not in ("Bank", "Cash"):
        raise ValidationError(
            "Bank reconciliation runs on Bank or Cash accounts", field="gl_account_id"
        )

    balance_per_books = Decimal(
        (
            await db.execute(
                select(func.coalesce(func.sum(GLEntry.debit - GLEntry.credit), 0)).where(
                    GLEntry.company_id == company_id,
                    GLEntry.account_id == gl_account_id,
                    GLEntry.posting_date <= as_of,
                )
            )
        ).scalar_one()
    )

    not_cleared = lambda col: (col.is_(None)) | (col > as_of)  # noqa: E731
    uncleared: list[BankReconUnclearedRow] = []

    payments = (
        (
            await db.execute(
                select(PaymentEntry).where(
                    PaymentEntry.company_id == company_id,
                    PaymentEntry.docstatus == 1,
                    PaymentEntry.posting_date <= as_of,
                    not_cleared(PaymentEntry.clearance_date),
                    (PaymentEntry.paid_from_id == gl_account_id)
                    | (PaymentEntry.paid_to_id == gl_account_id),
                )
            )
        )
        .scalars()
        .all()
    )
    for entry in payments:
        amount = ZERO
        if entry.paid_to_id == gl_account_id:
            amount += entry.received_amount * entry.target_exchange_rate
        if entry.paid_from_id == gl_account_id:
            amount -= entry.paid_amount * entry.source_exchange_rate
        uncleared.append(
            BankReconUnclearedRow(
                voucher_type="Payment Entry",
                voucher_id=entry.id,
                voucher_no=entry.name,
                posting_date=entry.posting_date,
                reference_no=entry.reference_no,
                amount=amount,
            )
        )

    je_rows = (
        await db.execute(
            select(
                JournalEntry,
                func.coalesce(
                    func.sum(JournalEntryAccount.debit - JournalEntryAccount.credit), 0
                ),
            )
            .join(JournalEntryAccount, JournalEntryAccount.journal_entry_id == JournalEntry.id)
            .where(
                JournalEntry.company_id == company_id,
                JournalEntry.docstatus == 1,
                JournalEntry.posting_date <= as_of,
                not_cleared(JournalEntry.clearance_date),
                JournalEntryAccount.account_id == gl_account_id,
            )
            .group_by(JournalEntry.id)
        )
    ).all()
    for je, amount in je_rows:
        uncleared.append(
            BankReconUnclearedRow(
                voucher_type="Journal Entry",
                voucher_id=je.id,
                voucher_no=je.name,
                posting_date=je.posting_date,
                reference_no=None,
                amount=Decimal(amount),
            )
        )

    uncleared.sort(key=lambda r: (r.posting_date, r.voucher_no))
    uncleared_amount = sum((r.amount for r in uncleared), ZERO)
    return BankReconciliationReport(
        gl_account_id=gl_account_id,
        as_of=as_of,
        balance_per_books=balance_per_books,
        uncleared_amount=uncleared_amount,
        balance_per_bank=balance_per_books - uncleared_amount,
        uncleared_entries=uncleared,
    )


# --- Sales / Purchase Register ----------------------------------------------------------------


