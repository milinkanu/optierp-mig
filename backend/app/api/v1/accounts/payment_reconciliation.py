"""Payment Reconciliation endpoints — Module 02.

A tool, not a stored document (erpnext payment_reconciliation): fetch a
party's outstanding invoices + unallocated payments, then post allocations.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_permission
from app.core.security import CurrentUser, get_tenant_db
from app.schemas.accounts import (
    PaymentReconciliationIn,
    PaymentReconciliationResponse,
    UnreconciledResponse,
)
from app.services import payment_reconciliation as service

router = APIRouter(prefix="/payment-reconciliation", tags=["accounts: payment reconciliation"])


@router.get(
    "/unreconciled",
    response_model=UnreconciledResponse,
    summary="Unreconciled invoices and payments for a party",
    description="Submitted invoices with outstanding > 0 and submitted payment "
    "entries with an unallocated remainder, for one customer or supplier.",
)
async def unreconciled(
    current_user: Annotated[CurrentUser, Depends(require_permission("Payment Entry", "read"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
    party_type: Annotated[str, Query(pattern="^(Customer|Supplier)$")],
    party_id: uuid.UUID,
) -> UnreconciledResponse:
    return await service.get_unreconciled(db, current_user.company_id, party_type, party_id)


@router.post(
    "/reconcile",
    response_model=PaymentReconciliationResponse,
    summary="Allocate payments against invoices",
    description="Each allocation links one payment entry's unallocated amount to "
    "one invoice and reduces the invoice outstanding. Example: `{'party_type': "
    "'Customer', 'party_id': '...', 'allocations': [{'payment_entry_id': '...', "
    "'invoice_type': 'Sales Invoice', 'invoice_id': '...', 'allocated_amount': 500}]}`",
)
async def reconcile(
    payload: PaymentReconciliationIn,
    current_user: Annotated[CurrentUser, Depends(require_permission("Payment Entry", "write"))],
    db: Annotated[AsyncSession, Depends(get_tenant_db)],
) -> PaymentReconciliationResponse:
    return await service.reconcile(db, payload, current_user)
