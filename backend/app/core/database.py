"""Async SQLAlchemy engine + session factory.

Multi-tenancy: the API connects as a non-owner PostgreSQL role so the
row-level-security policies created in the migrations apply. For every
request the active company id (from the JWT) is injected into the
transaction-local GUC ``app.company_id`` which the RLS policies read:

    CREATE POLICY company_isolation ON <table>
      USING (company_id = current_setting('app.company_id', true)::uuid);

Services additionally filter by company_id explicitly (defense in depth,
Section 2.1 rule 5).
"""

import uuid
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    echo=_settings.db_echo,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Plain session — used by auth endpoints that run before a company context exists."""
    async with async_session_factory() as session:
        yield session


async def set_company_context(session: AsyncSession, company_id: uuid.UUID | None) -> None:
    """Set the transaction-local tenant GUC consumed by RLS policies.

    ``set_config(..., is_local := true)`` scopes the value to the current
    transaction, so pooled connections never leak a tenant id.
    """
    await session.execute(
        text("SELECT set_config('app.company_id', :cid, true)"),
        {"cid": str(company_id) if company_id else ""},
    )
