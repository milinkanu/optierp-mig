"""Cross-document link validation for the buy/sell cycles.

One bound check covers every direction: for each linked source row,
``used + delta`` must stay within ``[0, cap]`` (with tolerance), where
``delta`` is the CUMULATIVE signed change a document applies to that row
(rows are aggregated first, so duplicate rows against the same source line
cannot slip through per-row checks; negative deltas — credit/debit notes —
are bounded by what was actually billed).

Called both at CREATE (from the payload) and again at SUBMIT (from the stored
rows, under the current DB state), so stale or duplicate drafts can no longer
over-receive / over-deliver / over-bill or post against cancelled orders.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.base import DOCSTATUS_SUBMITTED
from app.models.buying import PurchaseOrder, PurchaseOrderItem
from app.models.selling import SalesOrder, SalesOrderItem
from app.models.stock import (
    DeliveryNote,
    DeliveryNoteItem,
    PurchaseReceipt,
    PurchaseReceiptItem,
)

QTY_TOL = Decimal("0.000001")
AMT_TOL = Decimal("0.01")


@dataclass(frozen=True)
class LinkSpec:
    child_model: type
    parent_model: type
    parent_fk: str  # attribute on the child holding the parent id
    party_attr: str  # customer_id / supplier_id on the parent
    used_attr: str  # delivered_qty / received_qty / billed_qty / billed_amt
    cap_attr: str  # qty / amount
    doc_label: str
    check_currency: bool = False  # amount-based tracking needs same currency
    tolerance: Decimal = QTY_TOL


SO_DELIVERY = LinkSpec(SalesOrderItem, SalesOrder, "order_id", "customer_id",
                       "delivered_qty", "qty", "Sales Order")
PO_RECEIPT = LinkSpec(PurchaseOrderItem, PurchaseOrder, "order_id", "supplier_id",
                      "received_qty", "qty", "Purchase Order")
SO_BILLING = LinkSpec(SalesOrderItem, SalesOrder, "order_id", "customer_id",
                      "billed_amt", "amount", "Sales Order",
                      check_currency=True, tolerance=AMT_TOL)
PO_BILLING = LinkSpec(PurchaseOrderItem, PurchaseOrder, "order_id", "supplier_id",
                      "billed_amt", "amount", "Purchase Order",
                      check_currency=True, tolerance=AMT_TOL)
DN_BILLING = LinkSpec(DeliveryNoteItem, DeliveryNote, "delivery_note_id", "customer_id",
                      "billed_qty", "qty", "Delivery Note")
PR_BILLING = LinkSpec(PurchaseReceiptItem, PurchaseReceipt, "receipt_id", "supplier_id",
                      "billed_qty", "qty", "Purchase Receipt")


async def validate_link_deltas(
    db: AsyncSession,
    spec: LinkSpec,
    *,
    company_id: uuid.UUID,
    party_id: uuid.UUID,
    deltas: dict[uuid.UUID, Decimal],
    currency: str | None = None,
) -> dict[uuid.UUID, object]:
    """Validate cumulative per-row deltas against the linked source rows.
    Returns the loaded child rows keyed by id (for rate defaults etc.)."""
    if not deltas:
        return {}
    children = {
        c.id: c
        for c in (
            await db.execute(select(spec.child_model).where(spec.child_model.id.in_(deltas)))
        ).scalars()
    }
    missing = deltas.keys() - children.keys()
    if missing:
        raise NotFoundError(f"{spec.doc_label} item not found")
    parent_ids = {getattr(c, spec.parent_fk) for c in children.values()}
    parents = {
        p.id: p
        for p in (
            await db.execute(select(spec.parent_model).where(spec.parent_model.id.in_(parent_ids)))
        ).scalars()
    }
    for child in children.values():
        parent = parents.get(getattr(child, spec.parent_fk))
        if parent is None or parent.company_id != company_id \
                or getattr(parent, spec.party_attr) != party_id:
            raise ValidationError(
                f"Linked {spec.doc_label} belongs to a different party or company",
                field="items",
            )
        if parent.docstatus != DOCSTATUS_SUBMITTED:
            raise ValidationError(
                f"Linked {spec.doc_label} {parent.name} is not submitted", field="items"
            )
        if spec.check_currency and currency is not None and parent.currency != currency:
            raise ValidationError(
                f"{spec.doc_label} {parent.name} is in {parent.currency}; this document "
                f"is in {currency} — billing across currencies is not supported",
                field="currency",
            )
        used = getattr(child, spec.used_attr)
        cap = getattr(child, spec.cap_attr)
        new_used = used + deltas[child.id]
        if new_used < -spec.tolerance or new_used > cap + spec.tolerance:
            raise ValidationError(
                f"{spec.doc_label} {parent.name}: row would go to "
                f"{new_used} of {cap} ({spec.used_attr.replace('_', ' ')} is {used})",
                field="items",
            )
    return children


def aggregate(pairs: list[tuple[uuid.UUID | None, Decimal]]) -> dict[uuid.UUID, Decimal]:
    """Sum deltas per linked row id, skipping unlinked (None) entries."""
    out: dict[uuid.UUID, Decimal] = {}
    for link_id, delta in pairs:
        if link_id is not None:
            out[link_id] = out.get(link_id, Decimal("0")) + delta
    return out
