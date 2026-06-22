"""Reports — Sales/Purchase Register + Customer/Supplier Ledger Summary."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import (
    GLEntry,
    PurchaseInvoice,
    SalesInvoice,
)
from app.models.buying import Supplier
from app.models.selling import Customer
from app.schemas.accounts import (
    PartyLedgerSummaryRow,
    RegisterReport,
    RegisterRow,
)

from app.services.financial_reports._helpers import (
    ZERO,
)

async def _register(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    model: type,
    party_model: type,
    party_fk: str,
    party_name_col,
    from_date: date,
    to_date: date,
) -> RegisterReport:
    """All submitted invoices in a window with their net / tax / grand / outstanding —
    the daily 'what did we bill' list and the basis for GST returns."""
    result = (
        await db.execute(
            select(model, party_name_col)
            .join(party_model, party_model.id == getattr(model, party_fk))
            .where(
                model.company_id == company_id,
                model.docstatus == 1,
                model.is_opening.is_(False),
                model.posting_date >= from_date,
                model.posting_date <= to_date,
            )
            .order_by(model.posting_date, model.name)
        )
    ).all()
    rows: list[RegisterRow] = []
    total_net = total_tax = total_grand = total_out = ZERO
    for inv, party_name in result:
        rows.append(
            RegisterRow(
                voucher_id=inv.id,
                name=inv.name,
                posting_date=inv.posting_date,
                party_name=party_name,
                net_total=inv.net_total,
                total_taxes_and_charges=inv.total_taxes_and_charges,
                grand_total=inv.grand_total,
                outstanding_amount=inv.outstanding_amount,
                status=inv.status,
            )
        )
        total_net += inv.net_total
        total_tax += inv.total_taxes_and_charges
        total_grand += inv.grand_total
        total_out += inv.outstanding_amount
    return RegisterReport(
        rows=rows,
        total_net=total_net,
        total_tax=total_tax,
        total_grand=total_grand,
        total_outstanding=total_out,
    )


async def sales_register(
    db: AsyncSession, company_id: uuid.UUID, *, from_date: date, to_date: date
) -> RegisterReport:
    return await _register(
        db, company_id, model=SalesInvoice, party_model=Customer,
        party_fk="customer_id", party_name_col=Customer.customer_name,
        from_date=from_date, to_date=to_date,
    )


async def purchase_register(
    db: AsyncSession, company_id: uuid.UUID, *, from_date: date, to_date: date
) -> RegisterReport:
    return await _register(
        db, company_id, model=PurchaseInvoice, party_model=Supplier,
        party_fk="supplier_id", party_name_col=Supplier.supplier_name,
        from_date=from_date, to_date=to_date,
    )


# --- Customer / Supplier Ledger Summary -------------------------------------------------------


async def _party_ledger_summary(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    party_type: str,
    party_model: type,
    party_name_col,
    from_date: date,
    to_date: date,
) -> list[PartyLedgerSummaryRow]:
    """Per-party opening / period debit-credit / closing from the GL party rows —
    the backbone of a customer/supplier account statement."""
    opening_rows = dict(
        (
            await db.execute(
                select(
                    GLEntry.party_id,
                    func.coalesce(func.sum(GLEntry.debit - GLEntry.credit), 0),
                )
                .where(
                    GLEntry.company_id == company_id,
                    GLEntry.party_type == party_type,
                    GLEntry.posting_date < from_date,
                )
                .group_by(GLEntry.party_id)
            )
        ).all()
    )
    period_rows = (
        await db.execute(
            select(
                GLEntry.party_id,
                party_name_col,
                func.coalesce(func.sum(GLEntry.debit), 0),
                func.coalesce(func.sum(GLEntry.credit), 0),
            )
            .join(party_model, party_model.id == GLEntry.party_id)
            .where(
                GLEntry.company_id == company_id,
                GLEntry.party_type == party_type,
                GLEntry.posting_date >= from_date,
                GLEntry.posting_date <= to_date,
            )
            .group_by(GLEntry.party_id, party_name_col)
            .order_by(party_name_col)
        )
    ).all()

    rows: list[PartyLedgerSummaryRow] = []
    seen: set[uuid.UUID] = set()
    for party_id, party_name, debit, credit in period_rows:
        opening = Decimal(opening_rows.get(party_id, 0))
        debit = Decimal(debit)
        credit = Decimal(credit)
        seen.add(party_id)
        rows.append(
            PartyLedgerSummaryRow(
                party_id=party_id, party_name=party_name,
                opening=opening, debit=debit, credit=credit,
                closing=opening + debit - credit,
            )
        )
    # parties with only an opening balance (no movement in the window)
    leftover = {pid: bal for pid, bal in opening_rows.items() if pid not in seen and Decimal(bal) != ZERO}
    if leftover:
        names = dict(
            (
                await db.execute(
                    select(party_model.id, party_name_col).where(party_model.id.in_(leftover))
                )
            ).all()
        )
        for pid, bal in leftover.items():
            opening = Decimal(bal)
            rows.append(
                PartyLedgerSummaryRow(
                    party_id=pid, party_name=names.get(pid, str(pid)),
                    opening=opening, debit=ZERO, credit=ZERO, closing=opening,
                )
            )
        rows.sort(key=lambda r: r.party_name)
    return rows


async def customer_ledger_summary(
    db: AsyncSession, company_id: uuid.UUID, *, from_date: date, to_date: date
) -> list[PartyLedgerSummaryRow]:
    return await _party_ledger_summary(
        db, company_id, party_type="Customer", party_model=Customer,
        party_name_col=Customer.customer_name, from_date=from_date, to_date=to_date,
    )


async def supplier_ledger_summary(
    db: AsyncSession, company_id: uuid.UUID, *, from_date: date, to_date: date
) -> list[PartyLedgerSummaryRow]:
    return await _party_ledger_summary(
        db, company_id, party_type="Supplier", party_model=Supplier,
        party_name_col=Supplier.supplier_name, from_date=from_date, to_date=to_date,
    )


# --- Gross Profit -----------------------------------------------------------------------------


