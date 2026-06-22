"""Opening Invoice Creation Tool — bulk-load outstanding receivables/payables
that existed before go-live.

Each row becomes a minimal, submitted invoice flagged ``is_opening`` with a
single line booked to the company's **Temporary Opening** account (no income/
expense, no tax). Result: AR/AP aging shows the outstanding immediately, the
ledger stays balanced (Dr Receivable / Cr Temporary Opening for sales; the
mirror for purchase), and nothing leaks into the sales/purchase registers.

With ``create_missing_party`` the row's ``party_name`` is found-or-created, so a
migration list of debtors/creditors can be loaded without pre-creating each
party (ERPNext's "Create Missing Party").

The Temporary Opening account is later squared off against capital / retained
earnings with a normal Journal Entry as the rest of the opening balances
(cash, bank, fixed assets) are keyed in.
"""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.core.security import CurrentUser
from app.models.accounts import Account
from app.models.buying import Supplier
from app.models.selling import Customer
from app.schemas.accounts import (
    CustomerCreate,
    InvoiceItemIn,
    OpeningInvoiceResult,
    OpeningInvoiceRow,
    OpeningInvoiceTool,
    PurchaseInvoiceCreate,
    SalesInvoiceCreate,
    SupplierCreate,
)
from app.services import accounts_masters as masters
from app.services import purchase_invoice as pi
from app.services import sales_invoice as si


async def _temporary_opening_account(db: AsyncSession, company_id: uuid.UUID) -> uuid.UUID:
    account = await db.scalar(
        select(Account).where(
            Account.company_id == company_id,
            Account.account_type == "Temporary",
            Account.is_group.is_(False),
            Account.disabled.is_(False),
        )
    )
    if account is None:
        raise ValidationError(
            "No 'Temporary Opening' account found. Add a leaf account of type "
            "'Temporary' to your Chart of Accounts first (the India template ships one)."
        )
    return account.id


async def _resolve_party(
    db: AsyncSession,
    row: OpeningInvoiceRow,
    *,
    is_sales: bool,
    create_missing: bool,
    company_id: uuid.UUID,
    user: CurrentUser,
) -> uuid.UUID:
    """Pick the party: an explicit id wins; otherwise find-or-create by name when
    create_missing is on; otherwise it's an error pointing the user at the toggle."""
    if row.party_id is not None:
        return row.party_id

    name = (row.party_name or "").strip()
    if not name:
        raise ValidationError("Each row needs a party (pick one or enter a name)", field="rows")

    model = Customer if is_sales else Supplier
    name_col = Customer.customer_name if is_sales else Supplier.supplier_name
    existing = await db.scalar(
        select(model.id).where(model.company_id == company_id, func.lower(name_col) == name.lower())
    )
    if existing is not None:
        return existing
    if not create_missing:
        raise ValidationError(
            f"{'Customer' if is_sales else 'Supplier'} '{name}' not found — "
            "tick 'Create Missing Party' or pick an existing one.",
            field="rows",
        )
    if is_sales:
        created = await masters.create_customer(db, CustomerCreate(customer_name=name), user)
    else:
        created = await masters.create_supplier(db, SupplierCreate(supplier_name=name), user)
    return created.id


async def create_opening_invoices(
    db: AsyncSession, payload: OpeningInvoiceTool, user: CurrentUser
) -> OpeningInvoiceResult:
    if user.company_id is None:
        raise ValidationError("An active company is required")
    is_sales = payload.invoice_type == "sales"
    temp_opening_id = await _temporary_opening_account(db, user.company_id)

    created: list[str] = []
    for row in payload.rows:
        party_id = await _resolve_party(
            db, row, is_sales=is_sales, create_missing=payload.create_missing_party,
            company_id=user.company_id, user=user,
        )
        posting_date = row.posting_date or payload.posting_date
        due_date = row.due_date or posting_date
        item = InvoiceItemIn(
            item_name=row.item_name or "Opening Invoice",
            qty=Decimal("1"),
            rate=row.outstanding_amount,
            account_id=temp_opening_id,
        )
        if is_sales:
            invoice = await si.create_sales_invoice(
                db,
                SalesInvoiceCreate(
                    customer_id=party_id,
                    posting_date=posting_date,
                    due_date=due_date,
                    items=[item],
                    is_opening=True,
                    remarks=row.remarks,
                ),
                user,
            )
            invoice = await si.submit_sales_invoice(db, invoice.id, user)
        else:
            invoice = await pi.create_purchase_invoice(
                db,
                PurchaseInvoiceCreate(
                    supplier_id=party_id,
                    posting_date=posting_date,
                    due_date=due_date,
                    bill_no=row.bill_no,
                    items=[item],
                    is_opening=True,
                    remarks=row.remarks,
                ),
                user,
            )
            invoice = await pi.submit_purchase_invoice(db, invoice.id, user)
        created.append(invoice.name)

    return OpeningInvoiceResult(created=created, count=len(created))
