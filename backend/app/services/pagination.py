"""List pagination helper shared by all module services."""

from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

MAX_PAGE_SIZE = 200


async def paginate(
    db: AsyncSession, stmt: Select[Any], page: int = 1, page_size: int = 20
) -> tuple[list[Any], int]:
    """Execute ``stmt`` with limit/offset and return (rows, total_count)."""
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    total = (
        await db.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))
    ).scalar_one()
    rows = (await db.execute(stmt.limit(page_size).offset((page - 1) * page_size))).scalars().all()
    return list(rows), total
