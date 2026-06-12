"""Naming series engine — replaces Frappe's autoname / naming series.

Patterns follow ERPNext conventions, e.g. ``SINV-.YYYY.-`` or
``PO-.YYYY.-.MM.-.#####``:

  * literal text is kept as-is
  * ``.YYYY.`` / ``.YY.`` / ``.MM.`` / ``.DD.`` expand to the posting date
  * a trailing run of ``#`` sets the counter width (default 5)

Counters are stored per (expanded prefix, company) in the ``naming_series``
table and incremented atomically with INSERT ... ON CONFLICT ... RETURNING,
so two concurrent submissions can never receive the same name.
"""

import re
import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_DATE_TOKENS = {
    "YYYY": "%Y",
    "YY": "%y",
    "MM": "%m",
    "DD": "%d",
}

_HASH_RUN = re.compile(r"#+")


def expand_series(pattern: str, on_date: date | None = None) -> tuple[str, int]:
    """Resolve date tokens and counter width from a series pattern.

    Returns ``(expanded_prefix, digits)`` — e.g. ``("SINV-2026-", 5)`` for
    pattern ``SINV-.YYYY.-`` on a 2026 date.
    """
    on_date = on_date or date.today()
    digits = 5
    parts: list[str] = []
    for part in pattern.split("."):
        if part in _DATE_TOKENS:
            parts.append(on_date.strftime(_DATE_TOKENS[part]))
        elif _HASH_RUN.fullmatch(part):
            digits = len(part)
        else:
            parts.append(part)
    return "".join(parts), digits


def format_name(prefix: str, value: int, digits: int) -> str:
    return f"{prefix}{value:0{digits}d}"


async def get_next_name(
    db: AsyncSession,
    pattern: str,
    company_id: uuid.UUID,
    *,
    on_date: date | None = None,
) -> str:
    """Atomically reserve and format the next name in a series.

    The UPSERT both creates the counter row on first use and increments it
    on subsequent calls; RETURNING gives us the reserved value without a
    second round-trip. Row-level locking in PostgreSQL serialises concurrent
    increments of the same series.
    """
    prefix, digits = expand_series(pattern, on_date)
    result = await db.execute(
        text(
            """
            INSERT INTO naming_series (id, series_prefix, pattern, company_id, current_value)
            VALUES (gen_random_uuid(), :prefix, :pattern, :company_id, 1)
            ON CONFLICT (series_prefix, company_id)
            DO UPDATE SET current_value = naming_series.current_value + 1,
                          modified = now()
            RETURNING current_value
            """
        ),
        {"prefix": prefix, "pattern": pattern, "company_id": str(company_id)},
    )
    value = result.scalar_one()
    return format_name(prefix, value, digits)


async def peek_next_name(
    db: AsyncSession, pattern: str, company_id: uuid.UUID, *, on_date: date | None = None
) -> str:
    """Preview the next name without consuming it (for form display only)."""
    prefix, digits = expand_series(pattern, on_date)
    result = await db.execute(
        text(
            "SELECT current_value FROM naming_series "
            "WHERE series_prefix = :prefix AND company_id = :company_id"
        ),
        {"prefix": prefix, "company_id": str(company_id)},
    )
    current = result.scalar_one_or_none() or 0
    return format_name(prefix, current + 1, digits)
