"""Bank Reconciliation tool — Module 02.

Import bank-statement lines (Bank Transactions), then match each line to an
existing uncleared voucher (Payment Entry / Journal Entry). Matching sets the
voucher's ``clearance_date`` — the SAME mechanism the bank-reconciliation
report already keys off — so a matched line drops out of "uncleared" and
``balance_per_bank`` converges to the statement.

A Bank Transaction posts no GL of its own. MVP = one statement line ↔ one
voucher (amounts must agree within a cent). Deferred: split allocations, and
creating a new Payment/Journal Entry from an unmatched line (bank charges,
interest) — those need their own slice.
"""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.naming import get_next_name
from app.core.security import CurrentUser
from app.models.accounts import (
    Account,
    BankAccount,
    BankTransaction,
    GLEntry,
    JournalEntry,
    JournalEntryAccount,
    PaymentEntry,
    PurchaseInvoice,
    SalesInvoice,
)
from app.models.base import DOCSTATUS_CANCELLED
from app.models.buying import Supplier
from app.models.selling import Customer
from app.schemas.accounts import (
    BankReconciliationSummary,
    BankReconUnclearedRow,
    BankTransactionCreateVoucherIn,
    BankTransactionImportIn,
    BankTransactionMatchIn,
    BankTransactionPayInvoiceIn,
    InvoiceMatchSuggestion,
    JournalEntryAccountIn,
    JournalEntryCreate,
    PaymentEntryCreate,
    PaymentReferenceIn,
)
from app.services import journal_entry as je_service
from app.services import payment_entry as pe_service
from app.services.accounts_common import NAMING_SERIES, get_company
from app.services.audit import log_audit

ZERO = Decimal("0")
TOLERANCE = Decimal("0.01")  # a statement line and its voucher must agree to the cent


async def _get_bank_account(db: AsyncSession, account_id: uuid.UUID, company_id: uuid.UUID) -> BankAccount:
    ba = await db.get(BankAccount, account_id)
    if ba is None or ba.company_id != company_id:
        raise NotFoundError("Bank account not found")
    return ba


async def _get_transaction(db: AsyncSession, txn_id: uuid.UUID, company_id: uuid.UUID) -> BankTransaction:
    txn = await db.get(BankTransaction, txn_id)
    if txn is None or txn.company_id != company_id:
        raise NotFoundError("Bank transaction not found")
    return txn


def _signed(txn: BankTransaction) -> Decimal:
    """Statement line as a signed amount against the bank account: deposit +, withdrawal -."""
    return Decimal(txn.deposit) - Decimal(txn.withdrawal)


async def _uncleared_vouchers(
    db: AsyncSession, company_id: uuid.UUID, gl_account_id: uuid.UUID
) -> list[BankReconUnclearedRow]:
    """Submitted Payment Entries / Journal Entries touching this bank GL account
    that have not yet been cleared. ``amount`` is signed against the account
    (debit/inflow positive) — the same convention the bank-rec report uses."""
    rows: list[BankReconUnclearedRow] = []

    payments = (
        (
            await db.execute(
                select(PaymentEntry).where(
                    PaymentEntry.company_id == company_id,
                    PaymentEntry.docstatus == 1,
                    PaymentEntry.clearance_date.is_(None),
                    (PaymentEntry.paid_from_id == gl_account_id)
                    | (PaymentEntry.paid_to_id == gl_account_id),
                )
            )
        )
        .scalars()
        .all()
    )
    for pe in payments:
        amount = ZERO
        if pe.paid_to_id == gl_account_id:
            amount += Decimal(pe.received_amount) * Decimal(pe.target_exchange_rate)
        if pe.paid_from_id == gl_account_id:
            amount -= Decimal(pe.paid_amount) * Decimal(pe.source_exchange_rate)
        rows.append(
            BankReconUnclearedRow(
                voucher_type="Payment Entry", voucher_id=pe.id, voucher_no=pe.name,
                posting_date=pe.posting_date, reference_no=pe.reference_no, amount=amount,
            )
        )

    je_rows = (
        await db.execute(
            select(
                JournalEntry,
                func.coalesce(func.sum(JournalEntryAccount.debit - JournalEntryAccount.credit), 0),
            )
            .join(JournalEntryAccount, JournalEntryAccount.journal_entry_id == JournalEntry.id)
            .where(
                JournalEntry.company_id == company_id,
                JournalEntry.docstatus == 1,
                JournalEntry.clearance_date.is_(None),
                JournalEntryAccount.account_id == gl_account_id,
            )
            .group_by(JournalEntry.id)
        )
    ).all()
    for je, amount in je_rows:
        rows.append(
            BankReconUnclearedRow(
                voucher_type="Journal Entry", voucher_id=je.id, voucher_no=je.name,
                posting_date=je.posting_date, reference_no=None, amount=Decimal(amount),
            )
        )
    return rows


async def import_transactions(
    db: AsyncSession, payload: BankTransactionImportIn, user: CurrentUser
) -> list[BankTransaction]:
    """Bulk-create statement lines for a bank account (each line: deposit OR withdrawal)."""
    company = await get_company(db, user.company_id)
    ba = await _get_bank_account(db, payload.bank_account_id, company.id)

    created: list[BankTransaction] = []
    for row in payload.transactions:
        deposit, withdrawal = Decimal(row.deposit or 0), Decimal(row.withdrawal or 0)
        if deposit and withdrawal:
            raise ValidationError("A statement line is either a deposit or a withdrawal, not both")
        if not deposit and not withdrawal:
            raise ValidationError("A statement line needs a deposit or a withdrawal amount")
        name = await get_next_name(db, NAMING_SERIES["Bank Transaction"], company.id, on_date=row.date)
        txn = BankTransaction(
            id=uuid.uuid4(), company_id=company.id, name=name, bank_account_id=ba.id,
            date=row.date, description=row.description, reference_number=row.reference_number,
            deposit=deposit, withdrawal=withdrawal, status="Unreconciled", owner=user.id,
        )
        db.add(txn)
        created.append(txn)
    await db.flush()
    await log_audit(
        db, doctype="Bank Transaction", document_id=ba.id, action="IMPORT",
        user_id=user.id, company_id=company.id,
    )
    await db.commit()
    return created


async def list_transactions(
    db: AsyncSession, company_id: uuid.UUID, *, bank_account_id: uuid.UUID,
    status: str | None, page: int, page_size: int,
) -> tuple[list[BankTransaction], int]:
    base = select(BankTransaction).where(
        BankTransaction.company_id == company_id,
        BankTransaction.bank_account_id == bank_account_id,
    )
    if status:
        base = base.where(BankTransaction.status == status)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                base.order_by(BankTransaction.date, BankTransaction.name)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return rows, total


async def match_suggestions(
    db: AsyncSession, company_id: uuid.UUID, txn_id: uuid.UUID
) -> list[BankReconUnclearedRow]:
    """Uncleared vouchers whose signed amount equals this line's (within a cent),
    nearest statement date first."""
    txn = await _get_transaction(db, txn_id, company_id)
    ba = await _get_bank_account(db, txn.bank_account_id, company_id)
    if ba.gl_account_id is None:
        return []
    target = _signed(txn)
    candidates = [
        c for c in await _uncleared_vouchers(db, company_id, ba.gl_account_id)
        if abs(c.amount - target) <= TOLERANCE
    ]
    candidates.sort(key=lambda c: (abs((c.posting_date - txn.date).days), c.voucher_no))
    return candidates


async def reconcile(
    db: AsyncSession, company_id: uuid.UUID, txn_id: uuid.UUID,
    payload: BankTransactionMatchIn, user: CurrentUser,
) -> BankTransaction:
    """Match a line to one uncleared voucher: set the voucher's clearance_date
    (= the statement date) and mark the line Reconciled."""
    txn = await _get_transaction(db, txn_id, company_id)
    if txn.status == "Reconciled":
        raise ValidationError("This statement line is already reconciled")
    ba = await _get_bank_account(db, txn.bank_account_id, company_id)
    if ba.gl_account_id is None:
        raise ValidationError(
            "This bank account has no ledger account set — set it on the Bank Account first",
            field="bank_account_id",
        )

    candidates = await _uncleared_vouchers(db, company_id, ba.gl_account_id)
    match = next(
        (c for c in candidates
         if c.voucher_type == payload.voucher_type and c.voucher_id == payload.voucher_id),
        None,
    )
    if match is None:
        raise ValidationError(
            "That voucher is not an open (uncleared) entry on this bank account",
            field="voucher_id",
        )
    if abs(match.amount - _signed(txn)) > TOLERANCE:
        raise ValidationError(
            f"Amount mismatch — statement line is {_signed(txn)}, voucher is {match.amount}. "
            "Split/partial matches aren't supported yet.",
            field="voucher_id",
        )

    if payload.voucher_type == "Payment Entry":
        voucher = await db.get(PaymentEntry, payload.voucher_id)
    else:
        voucher = await db.get(JournalEntry, payload.voucher_id)
    voucher.clearance_date = txn.date
    voucher.modified_by = user.id

    txn.status = "Reconciled"
    txn.matched_voucher_type = payload.voucher_type
    txn.matched_voucher_id = payload.voucher_id
    txn.matched_voucher_no = match.voucher_no
    txn.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Bank Transaction", document_id=txn.id, action="RECONCILE",
        user_id=user.id, company_id=company_id,
    )
    await db.commit()
    return await _get_transaction(db, txn_id, company_id)


async def create_voucher(
    db: AsyncSession, company_id: uuid.UUID, txn_id: uuid.UUID,
    payload: BankTransactionCreateVoucherIn, user: CurrentUser,
) -> BankTransaction:
    """Create a Journal Entry for an UNMATCHED line (bank charges, interest, …).

    Posts the line's bank movement against ``account_id``: a deposit debits the
    bank and credits the contra account; a withdrawal does the reverse. The JE
    is submitted, cleared on the line's date, and matched to the line. Marked
    ``created_voucher`` so unreconcile cancels it.
    """
    txn = await _get_transaction(db, txn_id, company_id)
    if txn.status == "Reconciled":
        raise ValidationError("This statement line is already reconciled")
    ba = await _get_bank_account(db, txn.bank_account_id, company_id)
    if ba.gl_account_id is None:
        raise ValidationError(
            "This bank account has no ledger account set", field="bank_account_id"
        )
    if payload.account_id == ba.gl_account_id:
        raise ValidationError(
            "Pick a different account than the bank account itself", field="account_id"
        )

    is_deposit = Decimal(txn.deposit) > ZERO
    amount = Decimal(txn.deposit) if is_deposit else Decimal(txn.withdrawal)
    bank_gl = ba.gl_account_id
    if is_deposit:  # money in: Dr bank, Cr contra
        accounts = [
            JournalEntryAccountIn(account_id=bank_gl, debit=amount, cost_center_id=payload.cost_center_id),
            JournalEntryAccountIn(account_id=payload.account_id, credit=amount, cost_center_id=payload.cost_center_id),
        ]
    else:  # money out: Dr contra, Cr bank
        accounts = [
            JournalEntryAccountIn(account_id=payload.account_id, debit=amount, cost_center_id=payload.cost_center_id),
            JournalEntryAccountIn(account_id=bank_gl, credit=amount, cost_center_id=payload.cost_center_id),
        ]

    je = await je_service.create_journal_entry(
        db,
        JournalEntryCreate(
            posting_date=txn.date,
            remarks=payload.remarks or txn.description or f"Bank reconciliation — {txn.name}",
            accounts=accounts,
        ),
        user,
    )
    await je_service.submit_journal_entry(db, je.id, user)
    await je_service.set_clearance_date(db, je.id, txn.date, user)

    txn.status = "Reconciled"
    txn.matched_voucher_type = "Journal Entry"
    txn.matched_voucher_id = je.id
    txn.matched_voucher_no = je.name
    txn.created_voucher = True
    txn.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Bank Transaction", document_id=txn.id, action="CREATE_VOUCHER",
        user_id=user.id, company_id=company_id,
    )
    await db.commit()
    return await _get_transaction(db, txn_id, company_id)


async def invoice_suggestions(
    db: AsyncSession, company_id: uuid.UUID, txn_id: uuid.UUID
) -> list[InvoiceMatchSuggestion]:
    """Open invoices a line could settle — Sales for a deposit, Purchase for a
    withdrawal. Exact outstanding match first, then nearest, then oldest."""
    txn = await _get_transaction(db, txn_id, company_id)
    is_deposit = Decimal(txn.deposit) > ZERO
    amount = abs(_signed(txn))
    if is_deposit:
        model, party_model, party_fk, name_col, itype = (
            SalesInvoice, Customer, SalesInvoice.customer_id, Customer.customer_name, "Sales Invoice",
        )
    else:
        model, party_model, party_fk, name_col, itype = (
            PurchaseInvoice, Supplier, PurchaseInvoice.supplier_id, Supplier.supplier_name,
            "Purchase Invoice",
        )
    rows = (
        await db.execute(
            select(model, name_col)
            .join(party_model, party_model.id == party_fk)
            .where(
                model.company_id == company_id,
                model.docstatus == 1,
                model.outstanding_amount > 0,
                model.is_return.is_(False),
            )
        )
    ).all()
    suggestions = [
        InvoiceMatchSuggestion(
            invoice_type=itype, invoice_id=inv.id, name=inv.name, party_name=pname,
            posting_date=inv.posting_date, grand_total=inv.base_grand_total,
            outstanding_amount=inv.outstanding_amount,
        )
        for inv, pname in rows
    ]
    suggestions.sort(key=lambda s: (abs(s.outstanding_amount - amount), s.posting_date))
    return suggestions[:25]


async def pay_invoice(
    db: AsyncSession, company_id: uuid.UUID, txn_id: uuid.UUID,
    payload: BankTransactionPayInvoiceIn, user: CurrentUser,
) -> BankTransaction:
    """Settle an open invoice from a bank line: create + submit a Payment Entry
    (Receive for a deposit/Sales, Pay for a withdrawal/Purchase) allocated to the
    invoice, then clear it and match the line. The invoice's outstanding drops;
    any excess over the invoice sits as an on-account advance on the payment.
    Marked created_voucher so unmatch cancels the PE (restoring the invoice)."""
    txn = await _get_transaction(db, txn_id, company_id)
    if txn.status == "Reconciled":
        raise ValidationError("This statement line is already reconciled")
    ba = await _get_bank_account(db, txn.bank_account_id, company_id)
    if ba.gl_account_id is None:
        raise ValidationError(
            "This bank account has no ledger account set", field="bank_account_id"
        )

    is_deposit = Decimal(txn.deposit) > ZERO
    amount = Decimal(txn.deposit) if is_deposit else Decimal(txn.withdrawal)
    if is_deposit and payload.invoice_type != "Sales Invoice":
        raise ValidationError("A deposit settles a Sales Invoice", field="invoice_type")
    if not is_deposit and payload.invoice_type != "Purchase Invoice":
        raise ValidationError("A withdrawal settles a Purchase Invoice", field="invoice_type")

    inv = await db.get(SalesInvoice if is_deposit else PurchaseInvoice, payload.invoice_id)
    if inv is None or inv.company_id != company_id:
        raise NotFoundError("Invoice not found")
    outstanding = Decimal(inv.outstanding_amount)
    if outstanding <= ZERO:
        raise ValidationError("That invoice has nothing outstanding to settle", field="invoice_id")
    allocated = min(amount, outstanding)

    pe = await pe_service.create_payment_entry(
        db,
        PaymentEntryCreate(
            posting_date=txn.date,
            payment_type="Receive" if is_deposit else "Pay",
            party_type="Customer" if is_deposit else "Supplier",
            party_id=inv.customer_id if is_deposit else inv.supplier_id,
            paid_to_id=ba.gl_account_id if is_deposit else None,
            paid_from_id=None if is_deposit else ba.gl_account_id,
            paid_amount=amount,
            received_amount=amount,
            reference_no=txn.reference_number,
            reference_date=txn.date,
            mode_of_payment_id=payload.mode_of_payment_id,
            references=[
                PaymentReferenceIn(
                    reference_doctype=payload.invoice_type, reference_id=inv.id,
                    allocated_amount=allocated,
                )
            ],
        ),
        user,
    )
    pe_id, pe_name = pe.id, pe.name
    await pe_service.submit_payment_entry(db, pe_id, user)
    await pe_service.set_clearance_date(db, pe_id, txn.date, user)

    txn.status = "Reconciled"
    txn.matched_voucher_type = "Payment Entry"
    txn.matched_voucher_id = pe_id
    txn.matched_voucher_no = pe_name
    txn.created_voucher = True
    txn.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Bank Transaction", document_id=txn.id, action="PAY_INVOICE",
        user_id=user.id, company_id=company_id,
    )
    await db.commit()
    return await _get_transaction(db, txn_id, company_id)


async def unreconcile(
    db: AsyncSession, company_id: uuid.UUID, txn_id: uuid.UUID, user: CurrentUser
) -> BankTransaction:
    """Undo a match and free the line. If the tool created the voucher (from an
    unmatched line) and it's still live, cancel it (reversing its GL). If it's a
    pre-existing live voucher, just un-clear it. If the voucher was ALREADY
    cancelled or deleted out from under us, simply release the line — never try
    to re-cancel it (that would raise and leave the line stuck as Reconciled)."""
    txn = await _get_transaction(db, txn_id, company_id)
    if txn.status != "Reconciled" or txn.matched_voucher_id is None:
        raise ValidationError("This statement line is not reconciled")

    if txn.matched_voucher_type == "Payment Entry":
        voucher = await db.get(PaymentEntry, txn.matched_voucher_id)
    else:
        voucher = await db.get(JournalEntry, txn.matched_voucher_id)
    live = voucher is not None and voucher.docstatus != DOCSTATUS_CANCELLED

    if not live:
        pass  # already cancelled/gone — nothing to undo on the voucher
    elif txn.created_voucher:
        # the tool created this voucher from the line — cancel it (reverses GL,
        # and for a pay-invoice PE also restores the invoice's outstanding)
        if txn.matched_voucher_type == "Journal Entry":
            await je_service.cancel_journal_entry(db, txn.matched_voucher_id, user)
        else:
            await pe_service.cancel_payment_entry(db, txn.matched_voucher_id, user)
    else:
        voucher.clearance_date = None
        voucher.modified_by = user.id

    txn.status = "Unreconciled"
    txn.matched_voucher_type = None
    txn.matched_voucher_id = None
    txn.matched_voucher_no = None
    txn.created_voucher = False
    txn.modified_by = user.id
    await db.flush()
    await log_audit(
        db, doctype="Bank Transaction", document_id=txn.id, action="UNRECONCILE",
        user_id=user.id, company_id=company_id,
    )
    await db.commit()
    return await _get_transaction(db, txn_id, company_id)


async def release_matched_transactions(
    db: AsyncSession, voucher_type: str, voucher_id: uuid.UUID, *, user_id: uuid.UUID | None = None
) -> int:
    """Free any bank line matched to a voucher that is being cancelled — revert it
    to Unreconciled so it can be re-matched. Called from Payment Entry / Journal
    Entry cancel so a voucher cancelled from its OWN screen doesn't leave a stale
    "Reconciled" line pointing at a cancelled doc. Does not commit (caller does)."""
    rows = (
        (
            await db.execute(
                select(BankTransaction).where(
                    BankTransaction.matched_voucher_type == voucher_type,
                    BankTransaction.matched_voucher_id == voucher_id,
                )
            )
        )
        .scalars()
        .all()
    )
    for txn in rows:
        txn.status = "Unreconciled"
        txn.matched_voucher_type = None
        txn.matched_voucher_id = None
        txn.matched_voucher_no = None
        txn.created_voucher = False
        if user_id is not None:
            txn.modified_by = user_id
    await db.flush()
    return len(rows)


async def delete_transaction(
    db: AsyncSession, company_id: uuid.UUID, txn_id: uuid.UUID, user: CurrentUser
) -> None:
    """Remove a mis-imported line (must be unreconciled — unmatch first)."""
    txn = await _get_transaction(db, txn_id, company_id)
    if txn.status == "Reconciled":
        raise ValidationError("Unmatch this line before deleting it")
    await db.delete(txn)
    await db.commit()


async def summary(
    db: AsyncSession, company_id: uuid.UUID, bank_account_id: uuid.UUID
) -> BankReconciliationSummary:
    ba = await _get_bank_account(db, bank_account_id, company_id)

    counts = (
        await db.execute(
            select(BankTransaction.status, func.count(), func.coalesce(
                func.sum(BankTransaction.deposit - BankTransaction.withdrawal), 0
            ))
            .where(
                BankTransaction.company_id == company_id,
                BankTransaction.bank_account_id == bank_account_id,
            )
            .group_by(BankTransaction.status)
        )
    ).all()
    total = reconciled = unreconciled = 0
    unreconciled_amount = ZERO
    for status, n, net in counts:
        total += n
        if status == "Reconciled":
            reconciled += n
        else:
            unreconciled += n
            unreconciled_amount += Decimal(net)

    balance_per_books = balance_per_bank = ZERO
    if ba.gl_account_id is not None:
        account = await db.get(Account, ba.gl_account_id)
        if account is not None:
            balance_per_books = Decimal(
                (
                    await db.execute(
                        select(func.coalesce(func.sum(GLEntry.debit - GLEntry.credit), 0)).where(
                            GLEntry.company_id == company_id,
                            GLEntry.account_id == ba.gl_account_id,
                        )
                    )
                ).scalar_one()
            )
            uncleared = await _uncleared_vouchers(db, company_id, ba.gl_account_id)
            balance_per_bank = balance_per_books - sum((r.amount for r in uncleared), ZERO)

    return BankReconciliationSummary(
        bank_account_id=bank_account_id,
        gl_account_id=ba.gl_account_id,
        total=total,
        reconciled=reconciled,
        unreconciled=unreconciled,
        unreconciled_amount=unreconciled_amount,
        balance_per_books=balance_per_books,
        balance_per_bank=balance_per_bank,
    )
