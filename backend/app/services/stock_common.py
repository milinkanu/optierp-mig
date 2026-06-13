"""Shared helpers for Modules 03-05 document services."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.core import Company, SystemSetting
from app.models.stock import Bin, Item, ItemPrice, PriceList, Warehouse

ZERO = Decimal("0")

# ERPNext v15 default naming series per voucher
STOCK_NAMING_SERIES = {
    "Stock Entry": "MAT-STE-.YYYY.-",
    "Material Request": "MAT-MR-.YYYY.-",
    "Purchase Receipt": "MAT-PRE-.YYYY.-",
    "Delivery Note": "MAT-DN-.YYYY.-",
    "Purchase Order": "PUR-ORD-.YYYY.-",
    "Request for Quotation": "PUR-RFQ-.YYYY.-",
    "Supplier Quotation": "PUR-SQTN-.YYYY.-",
    "Quotation": "SAL-QTN-.YYYY.-",
    "Sales Order": "SAL-ORD-.YYYY.-",
}

ALLOW_NEGATIVE_STOCK_KEY = "allow_negative_stock"


async def get_item(
    db: AsyncSession, item_id: uuid.UUID, company_id: uuid.UUID, *, allow_disabled: bool = False
) -> Item:
    # select (not db.get) so the joined item_group eager load always runs —
    # identity-mapped instances from db.get skip it and later property access
    # would trigger a sync lazy-load (MissingGreenlet under asyncpg)
    item = await db.scalar(
        select(Item)
        .where(Item.id == item_id, Item.company_id == company_id)
        .execution_options(populate_existing=True)
    )
    if item is None:
        raise NotFoundError("Item not found")
    if item.disabled and not allow_disabled:
        raise ValidationError(f"Item '{item.item_code}' is disabled", field="item_id")
    return item


async def get_items(
    db: AsyncSession, item_ids: set[uuid.UUID], company_id: uuid.UUID,
    *, allow_disabled: bool = False,
) -> dict[uuid.UUID, Item]:
    items = {
        i.id: i
        for i in (
            await db.execute(
                select(Item).where(Item.id.in_(item_ids), Item.company_id == company_id)
            )
        ).scalars()
    }
    missing = item_ids - items.keys()
    if missing:
        raise NotFoundError(f"Item {next(iter(missing))} not found")
    if not allow_disabled:
        for item in items.values():
            if item.disabled:
                raise ValidationError(f"Item '{item.item_code}' is disabled", field="item_id")
    return items


async def get_warehouse(db: AsyncSession, warehouse_id: uuid.UUID, company_id: uuid.UUID) -> Warehouse:
    warehouse = await db.get(Warehouse, warehouse_id)
    if warehouse is None or warehouse.company_id != company_id:
        raise NotFoundError("Warehouse not found")
    if warehouse.is_group:
        raise ValidationError(
            f"Warehouse '{warehouse.warehouse_name}' is a group; use a leaf warehouse",
            field="warehouse_id",
        )
    if warehouse.disabled:
        raise ValidationError(f"Warehouse '{warehouse.warehouse_name}' is disabled", field="warehouse_id")
    return warehouse


async def allow_negative_stock(db: AsyncSession, company_id: uuid.UUID) -> bool:
    setting = await db.scalar(
        select(SystemSetting).where(
            SystemSetting.key == ALLOW_NEGATIVE_STOCK_KEY, SystemSetting.company_id == company_id
        )
    )
    # strict: only JSON true enables it ("false"/"0" strings must not)
    return setting is not None and setting.value is True


async def get_bin_for_update(
    db: AsyncSession, company_id: uuid.UUID, item_id: uuid.UUID, warehouse_id: uuid.UUID
) -> Bin:
    """Row-locked Bin (created on first touch) — serialises concurrent valuation.

    First touch races are absorbed by ON CONFLICT DO NOTHING + re-select, so two
    concurrent vouchers creating the same bin never 500 on the unique key.
    """
    bin_row = await db.scalar(
        select(Bin)
        .where(Bin.item_id == item_id, Bin.warehouse_id == warehouse_id)
        .with_for_update()
    )
    if bin_row is None:
        await db.execute(
            pg_insert(Bin)
            .values(company_id=company_id, item_id=item_id, warehouse_id=warehouse_id)
            .on_conflict_do_nothing(index_elements=["item_id", "warehouse_id"])
        )
        bin_row = await db.scalar(
            select(Bin)
            .where(Bin.item_id == item_id, Bin.warehouse_id == warehouse_id)
            .with_for_update()
        )
    return bin_row


def inventory_account_for(company: Company, warehouse: Warehouse) -> uuid.UUID:
    account_id = warehouse.account_id or company.default_inventory_account_id
    if account_id is None:
        raise ValidationError(
            "No inventory account configured (warehouse or company default). "
            "Set one on the company or disable perpetual inventory."
        )
    return account_id


async def resolve_item_rate(
    db: AsyncSession,
    item: Item,
    *,
    buying: bool,
    price_list_id: uuid.UUID | None = None,
    on_date: date | None = None,
    currency: str | None = None,
) -> tuple[Decimal, str]:
    """Default line rate: matching Item Price first, then the item master
    (erpnext get_item_details, simplified — no pricing rules / UOM conversion).
    When ``currency`` is given, only price lists in that currency match."""
    on_date = on_date or date.today()
    stmt = (
        select(ItemPrice)
        .join(PriceList, PriceList.id == ItemPrice.price_list_id)
        .where(
            ItemPrice.item_id == item.id,
            PriceList.enabled.is_(True),
            PriceList.buying.is_(True) if buying else PriceList.selling.is_(True),
        )
        .order_by(ItemPrice.valid_from.desc().nulls_last())
    )
    if currency is not None:
        stmt = stmt.where(PriceList.currency == currency.upper())
    if price_list_id is not None:
        stmt = stmt.where(ItemPrice.price_list_id == price_list_id)
    for price in (await db.execute(stmt)).scalars():
        if price.valid_from and price.valid_from > on_date:
            continue
        if price.valid_upto and price.valid_upto < on_date:
            continue
        return price.price_list_rate, "Item Price"
    if buying:
        if item.last_purchase_rate > ZERO:
            return item.last_purchase_rate, "Last Purchase Rate"
        return item.valuation_rate, "Valuation Rate"
    return item.standard_rate, "Standard Rate"


def require_stock_item(item: Item) -> None:
    if not item.is_stock_item:
        raise ValidationError(
            f"Item '{item.item_code}' is not a stock item", field="item_id"
        )
