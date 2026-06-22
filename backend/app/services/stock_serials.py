"""Serial No lifecycle (Phase 5).

The single place serial numbers are created, moved between statuses, and reverted.
Serials are a tracking layer only — valuation stays Moving Average on the Bin.
Each stock document parses its line's serial_nos and, AFTER make_sl_entries, calls
the matching transition; cancel calls the inverse. Availability for delivery /
issue / transfer / supplier-return is status "In Stock" at the right warehouse.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.stock import Item, SerialNo
from app.services.pagination import paginate

ZERO = Decimal("0")
_UNSET = object()  # sentinel: "leave this attribute unchanged"


def parse_serials(serial_nos: list[str] | None) -> list[str]:
    """Clean a serial list: strip, drop blanks, reject within-line duplicates."""
    if not serial_nos:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in serial_nos:
        s = (raw or "").strip()
        if not s:
            continue
        if s in seen:
            raise ValidationError(
                f"Duplicate serial number '{s}' in the same line", field="serial_nos"
            )
        seen.add(s)
        cleaned.append(s)
    return cleaned


def serials_to_text(serials: list[str]) -> str | None:
    return "\n".join(serials) if serials else None


def serials_from_text(text: str | None) -> list[str]:
    if not text:
        return []
    return [s.strip() for s in text.replace("\r", "").split("\n") if s.strip()]


def validate_line_serials(item: Item, serials: list[str], stock_qty: Decimal) -> None:
    """Count rule: a serialised line must list exactly stock_qty serials; a
    non-serialised item must not carry any."""
    if item.has_serial_no:
        if Decimal(len(serials)) != stock_qty:
            raise ValidationError(
                f"Item '{item.item_code}' is serialised: list exactly {stock_qty} serial "
                f"number(s) (got {len(serials)})",
                field="serial_nos",
            )
    elif serials:
        raise ValidationError(
            f"Item '{item.item_code}' is not serialised; remove the serial numbers",
            field="serial_nos",
        )


async def _load(
    db: AsyncSession, company_id: uuid.UUID, item_id: uuid.UUID, serials: list[str]
) -> dict[str, SerialNo]:
    rows = (
        await db.execute(
            select(SerialNo).where(
                SerialNo.company_id == company_id,
                SerialNo.item_id == item_id,
                SerialNo.serial_no.in_(serials),
            )
        )
    ).scalars().all()
    return {r.serial_no: r for r in rows}


async def _load_company(
    db: AsyncSession, company_id: uuid.UUID, serials: list[str]
) -> dict[str, SerialNo]:
    """Look up serials company-wide, ignoring item. Serials are unique per
    company across ALL items (the uq_serial_no constraint), so the receipt
    duplicate check must be company-wide — not item-scoped — to surface a clean
    ValidationError instead of a raw IntegrityError on the DB constraint."""
    rows = (
        await db.execute(
            select(SerialNo).where(
                SerialNo.company_id == company_id,
                SerialNo.serial_no.in_(serials),
            )
        )
    ).scalars().all()
    return {r.serial_no: r for r in rows}


async def create_serials(
    db: AsyncSession, company_id: uuid.UUID, item_id: uuid.UUID, warehouse_id: uuid.UUID | None,
    serials: list[str], *, voucher_type: str, voucher_id: uuid.UUID,
) -> None:
    """Receipt: create each serial 'In Stock'. Each must be new (unique per company,
    across all items). A flush after the insert makes a later line in the SAME
    document see these rows (the session is autoflush=False), so a duplicate serial
    across two lines surfaces as a clean ValidationError rather than a 500."""
    if not serials:
        return
    existing = await _load_company(db, company_id, serials)
    if existing:
        raise ValidationError(
            f"Serial number(s) already exist: {', '.join(sorted(existing))}", field="serial_nos"
        )
    for s in serials:
        db.add(
            SerialNo(
                company_id=company_id, serial_no=s, item_id=item_id, warehouse_id=warehouse_id,
                status="In Stock", purchase_voucher_type=voucher_type, purchase_voucher_id=voucher_id,
            )
        )
    await db.flush()


async def delete_serials(
    db: AsyncSession, company_id: uuid.UUID, item_id: uuid.UUID, serials: list[str], *,
    warehouse_match: uuid.UUID | None = None,
) -> None:
    """Cancel a receipt: remove the serials it created. Blocked if any has since
    left stock (e.g. been delivered) or moved to another warehouse — mirrors the
    SLE cancel-honesty guard so a receipt can't be un-done once its units moved on."""
    if not serials:
        return
    found = await _load(db, company_id, item_id, serials)
    for s in serials:
        sn = found.get(s)
        if sn is None:
            raise ValidationError(f"Serial number '{s}' not found", field="serial_nos")
        if sn.status != "In Stock":
            raise ValidationError(
                f"Cannot cancel: serial '{s}' is '{sn.status}' (no longer in stock). "
                f"Reverse the later document first.",
                field="serial_nos",
            )
        if warehouse_match is not None and sn.warehouse_id != warehouse_match:
            raise ValidationError(
                f"Cannot cancel: serial '{s}' has since moved to another warehouse. "
                f"Reverse the later document first.",
                field="serial_nos",
            )
        await db.delete(sn)


async def move_serials(
    db: AsyncSession, company_id: uuid.UUID, item_id: uuid.UUID, serials: list[str], *,
    from_status: str, to_status: str, warehouse_match: uuid.UUID | None = None,
    delivery_voucher_match: uuid.UUID | None = None,
    purchase_voucher_match: uuid.UUID | None = None,
    set_warehouse: object = _UNSET, set_delivery_voucher: object = _UNSET,
) -> None:
    """Flip each serial from one status to another, validating existence + current
    status (+ optional warehouse / delivering-voucher / receiving-voucher).
    Optionally re-home the warehouse / delivery link.

    ``delivery_voucher_match`` binds a delivery's serials to that DN: a return must
    only restock a serial the *original* DN actually shipped, and the cancel of a
    delivery must not silently revert a serial since re-delivered by another doc.
    ``purchase_voucher_match`` is the mirror for a supplier return: only a serial
    received on the *original* receipt may be returned against it."""
    if not serials:
        return
    found = await _load(db, company_id, item_id, serials)
    for s in serials:
        sn = found.get(s)
        if sn is None:
            raise ValidationError(f"Serial number '{s}' not found for this item", field="serial_nos")
        if sn.status != from_status:
            raise ValidationError(
                f"Serial '{s}' is '{sn.status}' but must be '{from_status}' for this action",
                field="serial_nos",
            )
        if warehouse_match is not None and sn.warehouse_id != warehouse_match:
            raise ValidationError(
                f"Serial '{s}' is not in the selected warehouse", field="serial_nos"
            )
        if delivery_voucher_match is not None and sn.delivery_voucher_id != delivery_voucher_match:
            raise ValidationError(
                f"Serial '{s}' was not delivered by the document being returned against",
                field="serial_nos",
            )
        if purchase_voucher_match is not None and sn.purchase_voucher_id != purchase_voucher_match:
            raise ValidationError(
                f"Serial '{s}' was not received on the receipt being returned against",
                field="serial_nos",
            )
        sn.status = to_status
        if set_warehouse is not _UNSET:
            sn.warehouse_id = set_warehouse  # type: ignore[assignment]
        if set_delivery_voucher is not _UNSET:
            sn.delivery_voucher_id = set_delivery_voucher  # type: ignore[assignment]


# --- read API (serials are created by transactions, not free-form CRUD) ---------------------


async def list_serial_nos(
    db: AsyncSession, company_id: uuid.UUID | None, page: int = 1, page_size: int = 20,
    item_id: uuid.UUID | None = None, status: str | None = None,
    warehouse_id: uuid.UUID | None = None, search: str | None = None,
) -> tuple[list[SerialNo], int]:
    stmt = select(SerialNo).where(SerialNo.company_id == company_id).order_by(SerialNo.serial_no)
    if item_id is not None:
        stmt = stmt.where(SerialNo.item_id == item_id)
    if status:
        stmt = stmt.where(SerialNo.status == status)
    if warehouse_id is not None:
        stmt = stmt.where(SerialNo.warehouse_id == warehouse_id)
    if search:
        stmt = stmt.where(SerialNo.serial_no.ilike(f"%{search}%"))
    return await paginate(db, stmt, page, page_size)


async def get_serial_no(
    db: AsyncSession, serial_id: uuid.UUID, company_id: uuid.UUID | None
) -> SerialNo:
    sn = await db.scalar(
        select(SerialNo).where(SerialNo.id == serial_id, SerialNo.company_id == company_id)
    )
    if sn is None:
        raise NotFoundError("Serial No not found")
    return sn
