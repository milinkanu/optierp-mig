"""Bank Reconciliation tool endpoints — Module 02.

Import bank-statement lines, then match each to an uncleared Payment Entry /
Journal Entry (which sets that voucher's clearance_date). Read-only balance
maths stay in the existing /reports/bank-reconciliation report.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.accounts import (
    BankReconciliationSummary,
    BankReconUnclearedRow,
    BankTransactionCreateVoucherIn,
    BankTransactionImportIn,
    BankTransactionMatchIn,
    BankTransactionPayInvoiceIn,
    BankTransactionResponse,
    InvoiceMatchSuggestion,
)
from app.schemas.common import ListResponse
from app.services import bank_reconciliation_tool as service

router = APIRouter(prefix="/bank-transactions", tags=["accounts: bank reconciliation"])


@router.post(
    "/import",
    response_model=list[BankTransactionResponse],
    status_code=201,
    summary="Import bank-statement lines",
    description="Bulk-create Bank Transactions for a bank account. Each line is a "
    "deposit OR a withdrawal. Lines start Unreconciled.",
)
async def import_transactions(
    payload: BankTransactionImportIn,
    current_user: Annotated[CurrentUser, Depends(require_permission("Bank Transaction", "create"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> list[BankTransactionResponse]:
    created = await service.import_transactions(db, payload, current_user)
    return [BankTransactionResponse.model_validate(t) for t in created]


@router.get(
    "",
    response_model=ListResponse[BankTransactionResponse],
    summary="List bank transactions for an account",
    description="Filter by status (Unreconciled | Reconciled). Oldest first.",
)
async def list_transactions(
    current_user: Annotated[CurrentUser, Depends(require_permission("Bank Transaction", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    bank_account_id: uuid.UUID,
    status: Annotated[str | None, Query(pattern="^(Unreconciled|Reconciled)$")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ListResponse[BankTransactionResponse]:
    rows, total = await service.list_transactions(
        db, current_user.company_id, bank_account_id=bank_account_id,
        status=status, page=page, page_size=page_size,
    )
    return ListResponse(
        items=[BankTransactionResponse.model_validate(t) for t in rows],
        total=total, page=page, page_size=page_size,
    )


@router.get(
    "/summary",
    response_model=BankReconciliationSummary,
    summary="Reconciliation progress + balances for a bank account",
)
async def get_summary(
    current_user: Annotated[CurrentUser, Depends(require_permission("Bank Transaction", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    bank_account_id: uuid.UUID,
) -> BankReconciliationSummary:
    return await service.summary(db, current_user.company_id, bank_account_id)


@router.get(
    "/{txn_id}/match-suggestions",
    response_model=list[BankReconUnclearedRow],
    summary="Suggested vouchers to match a statement line",
    description="Uncleared Payment Entries / Journal Entries on this bank account "
    "whose amount equals the line (within a cent), nearest date first.",
)
async def match_suggestions(
    txn_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Bank Transaction", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> list[BankReconUnclearedRow]:
    return await service.match_suggestions(db, current_user.company_id, txn_id)


@router.post(
    "/{txn_id}/reconcile",
    response_model=BankTransactionResponse,
    summary="Match a statement line to a voucher",
    description="Sets the voucher's clearance_date and marks the line Reconciled. "
    "Amounts must agree to the cent.",
)
async def reconcile(
    txn_id: uuid.UUID,
    payload: BankTransactionMatchIn,
    current_user: Annotated[CurrentUser, Depends(require_permission("Bank Transaction", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> BankTransactionResponse:
    return BankTransactionResponse.model_validate(
        await service.reconcile(db, current_user.company_id, txn_id, payload, current_user)
    )


@router.get(
    "/{txn_id}/invoice-suggestions",
    response_model=list[InvoiceMatchSuggestion],
    summary="Open invoices a line could settle",
    description="Sales invoices for a deposit, Purchase invoices for a withdrawal — those with "
    "outstanding > 0, exact-amount match first.",
)
async def invoice_suggestions(
    txn_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Bank Transaction", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> list[InvoiceMatchSuggestion]:
    return await service.invoice_suggestions(db, current_user.company_id, txn_id)


@router.post(
    "/{txn_id}/pay-invoice",
    response_model=BankTransactionResponse,
    summary="Settle an open invoice from a bank line",
    description="Creates + submits a Payment Entry (Receive/Pay) allocated to the chosen invoice, "
    "clears it, and matches the line. The invoice's outstanding drops automatically.",
)
async def pay_invoice(
    txn_id: uuid.UUID,
    payload: BankTransactionPayInvoiceIn,
    current_user: Annotated[CurrentUser, Depends(require_permission("Bank Transaction", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> BankTransactionResponse:
    return BankTransactionResponse.model_validate(
        await service.pay_invoice(db, current_user.company_id, txn_id, payload, current_user)
    )


@router.post(
    "/{txn_id}/create-voucher",
    response_model=BankTransactionResponse,
    summary="Create a Journal Entry from an unmatched line",
    description="For lines with no existing voucher (bank charges, interest, …). Posts the "
    "bank movement against the chosen contra account, submits + clears the JE, and matches it.",
)
async def create_voucher(
    txn_id: uuid.UUID,
    payload: BankTransactionCreateVoucherIn,
    current_user: Annotated[CurrentUser, Depends(require_permission("Bank Transaction", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> BankTransactionResponse:
    return BankTransactionResponse.model_validate(
        await service.create_voucher(db, current_user.company_id, txn_id, payload, current_user)
    )


@router.post(
    "/{txn_id}/unreconcile",
    response_model=BankTransactionResponse,
    summary="Undo a match",
    description="Clears the matched voucher's clearance_date and re-opens the line. If the tool "
    "created the voucher (from an unmatched line), it is cancelled.",
)
async def unreconcile(
    txn_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Bank Transaction", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> BankTransactionResponse:
    return BankTransactionResponse.model_validate(
        await service.unreconcile(db, current_user.company_id, txn_id, current_user)
    )


@router.delete(
    "/{txn_id}",
    status_code=204,
    summary="Delete a mis-imported line",
    description="Only allowed when the line is unreconciled (unmatch it first).",
)
async def delete_transaction(
    txn_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("Bank Transaction", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> None:
    await service.delete_transaction(db, current_user.company_id, txn_id, current_user)
