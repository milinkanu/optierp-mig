"""Idempotent bootstrap seeding: masters, roles, default permissions, admin user.

Usage:
    python -m scripts.seed --admin-email admin@example.com --admin-password <pw>

(or set ADMIN_EMAIL / ADMIN_PASSWORD environment variables)
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import async_session_factory  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.core import (  # noqa: E402
    Country,
    Currency,
    Role,
    RolePermission,
    UOM,
    User,
    UserRole,
)

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seeds"

# Default permission matrix: (role, doctype, allowed actions).
# Extended by later modules as their doctypes are migrated.
_ACCOUNTS_TXN_ALL = ["read", "write", "create", "submit", "cancel", "amend", "print", "email", "report"]
_ACCOUNTS_TXN_USER = ["read", "write", "create", "submit", "print", "email", "report"]

DEFAULT_PERMISSIONS: list[tuple[str, str, list[str]]] = [
    # Module 01 — Core / Setup
    ("Accounts Manager", "Company", ["read"]),
    ("Accounts Manager", "Account", ["read", "write", "create", "report"]),
    ("Accounts Manager", "Currency", ["read"]),
    ("Accounts Manager", "Currency Exchange", ["read", "write", "create"]),
    ("Accounts User", "Company", ["read"]),
    ("Accounts User", "Account", ["read", "report"]),
    ("Accounts User", "Currency", ["read"]),
    ("Accounts User", "Currency Exchange", ["read"]),
    ("Stock Manager", "UOM", ["read", "write", "create"]),
    ("Stock User", "UOM", ["read"]),
    ("Employee", "Company", ["read"]),
    # Module 02 — Accounts
    ("Accounts Manager", "Customer", ["read", "write", "create", "report"]),
    ("Accounts Manager", "Supplier", ["read", "write", "create", "report"]),
    ("Accounts Manager", "Tax Category", ["read", "write", "create"]),
    ("Accounts Manager", "Tax Template", ["read", "write", "create"]),
    ("Accounts Manager", "Budget", ["read", "write", "create", "submit", "cancel", "report"]),
    ("Accounts Manager", "Journal Entry", _ACCOUNTS_TXN_ALL),
    ("Accounts Manager", "Sales Invoice", _ACCOUNTS_TXN_ALL),
    ("Accounts Manager", "Purchase Invoice", _ACCOUNTS_TXN_ALL),
    ("Accounts Manager", "Payment Entry", _ACCOUNTS_TXN_ALL),
    ("Accounts Manager", "Period Closing Voucher", ["read", "create", "submit"]),
    ("Accounts Manager", "GL Entry", ["read", "report"]),
    ("Accounts User", "Customer", ["read"]),
    ("Accounts User", "Supplier", ["read"]),
    ("Accounts User", "Tax Category", ["read"]),
    ("Accounts User", "Tax Template", ["read"]),
    ("Accounts User", "Budget", ["read"]),
    ("Accounts User", "Journal Entry", _ACCOUNTS_TXN_USER),
    ("Accounts User", "Sales Invoice", _ACCOUNTS_TXN_USER),
    ("Accounts User", "Purchase Invoice", _ACCOUNTS_TXN_USER),
    ("Accounts User", "Payment Entry", _ACCOUNTS_TXN_USER),
    ("Accounts User", "GL Entry", ["read", "report"]),
    ("Sales User", "Customer", ["read", "write", "create"]),
    ("Sales User", "Sales Invoice", ["read", "create", "print", "report"]),
    ("Purchase User", "Supplier", ["read", "write", "create"]),
    ("Purchase User", "Purchase Invoice", ["read", "create", "print", "report"]),
    # Module 03 — Stock
    ("Stock Manager", "Item Group", ["read", "write", "create"]),
    ("Stock Manager", "Warehouse", ["read", "write", "create"]),
    ("Stock Manager", "Item", ["read", "write", "create", "report"]),
    ("Stock Manager", "Price List", ["read", "write", "create"]),
    ("Stock Manager", "Item Price", ["read", "write", "create"]),
    ("Stock Manager", "Stock Entry", _ACCOUNTS_TXN_ALL),
    ("Stock Manager", "Material Request", _ACCOUNTS_TXN_ALL),
    ("Stock Manager", "Purchase Receipt", _ACCOUNTS_TXN_ALL),
    ("Stock Manager", "Delivery Note", _ACCOUNTS_TXN_ALL),
    ("Stock Manager", "Stock Ledger Entry", ["read", "report"]),
    ("Stock User", "Item Group", ["read"]),
    ("Stock User", "Warehouse", ["read"]),
    ("Stock User", "Item", ["read", "report"]),
    ("Stock User", "Price List", ["read"]),
    ("Stock User", "Item Price", ["read"]),
    ("Stock User", "Stock Entry", _ACCOUNTS_TXN_USER),
    ("Stock User", "Material Request", _ACCOUNTS_TXN_USER),
    ("Stock User", "Purchase Receipt", _ACCOUNTS_TXN_USER),
    ("Stock User", "Delivery Note", _ACCOUNTS_TXN_USER),
    ("Stock User", "Stock Ledger Entry", ["read", "report"]),
    # Module 04 — Buying
    ("Purchase Manager", "Supplier", ["read", "write", "create", "report"]),
    ("Purchase Manager", "Item", ["read", "report"]),
    ("Purchase Manager", "Warehouse", ["read"]),
    ("Purchase Manager", "Purchase Order", _ACCOUNTS_TXN_ALL),
    ("Purchase Manager", "Request for Quotation", _ACCOUNTS_TXN_ALL),
    ("Purchase Manager", "Supplier Quotation", _ACCOUNTS_TXN_ALL),
    ("Purchase Manager", "Purchase Receipt", _ACCOUNTS_TXN_ALL),
    ("Purchase Manager", "Purchase Invoice", _ACCOUNTS_TXN_ALL),
    ("Purchase Manager", "Material Request", _ACCOUNTS_TXN_ALL),
    ("Purchase Manager", "Stock Ledger Entry", ["read", "report"]),
    ("Purchase User", "Item", ["read"]),
    ("Purchase User", "Warehouse", ["read"]),
    ("Purchase User", "Purchase Order", _ACCOUNTS_TXN_USER),
    ("Purchase User", "Request for Quotation", _ACCOUNTS_TXN_USER),
    ("Purchase User", "Supplier Quotation", _ACCOUNTS_TXN_USER),
    ("Purchase User", "Purchase Receipt", _ACCOUNTS_TXN_USER),
    ("Purchase User", "Material Request", _ACCOUNTS_TXN_USER),
    # Module 05 — Selling
    ("Sales Manager", "Customer", ["read", "write", "create", "report"]),
    ("Sales Manager", "Item", ["read", "report"]),
    ("Sales Manager", "Warehouse", ["read"]),
    ("Sales Manager", "Quotation", _ACCOUNTS_TXN_ALL),
    ("Sales Manager", "Sales Order", _ACCOUNTS_TXN_ALL),
    ("Sales Manager", "Delivery Note", _ACCOUNTS_TXN_ALL),
    ("Sales Manager", "Sales Invoice", _ACCOUNTS_TXN_ALL),
    ("Sales Manager", "Stock Ledger Entry", ["read", "report"]),
    ("Sales User", "Item", ["read"]),
    ("Sales User", "Warehouse", ["read"]),
    ("Sales User", "Quotation", _ACCOUNTS_TXN_USER),
    ("Sales User", "Sales Order", _ACCOUNTS_TXN_USER),
    ("Sales User", "Delivery Note", _ACCOUNTS_TXN_USER),
    # Accounts roles need read access to the new doctypes for invoice linking
    ("Accounts Manager", "Item", ["read"]),
    ("Accounts Manager", "Purchase Order", ["read", "report"]),
    ("Accounts Manager", "Purchase Receipt", ["read", "report"]),
    ("Accounts Manager", "Sales Order", ["read", "report"]),
    ("Accounts Manager", "Delivery Note", ["read", "report"]),
    ("Accounts User", "Item", ["read"]),
    ("Accounts User", "Purchase Order", ["read"]),
    ("Accounts User", "Purchase Receipt", ["read"]),
    ("Accounts User", "Sales Order", ["read"]),
    ("Accounts User", "Delivery Note", ["read"]),
]


def _load(name: str) -> list[dict]:
    return json.loads((SEED_DIR / name).read_text(encoding="utf-8"))


async def seed_masters(db: AsyncSession) -> None:
    existing_currencies = set((await db.execute(select(Currency.code))).scalars().all())
    for row in _load("currencies.json"):
        if row["code"] not in existing_currencies:
            db.add(Currency(**row))

    existing_countries = set((await db.execute(select(Country.code))).scalars().all())
    for row in _load("countries.json"):
        if row["code"] not in existing_countries:
            db.add(Country(**row))

    existing_uoms = set((await db.execute(select(UOM.uom_name))).scalars().all())
    for row in _load("uoms.json"):
        if row["uom_name"] not in existing_uoms:
            db.add(UOM(**row))

    existing_roles = set((await db.execute(select(Role.name))).scalars().all())
    for row in _load("roles.json"):
        if row["name"] not in existing_roles:
            db.add(Role(**row))
    await db.flush()


async def seed_permissions(db: AsyncSession) -> None:
    for role, doctype, actions in DEFAULT_PERMISSIONS:
        perm = await db.scalar(
            select(RolePermission).where(
                RolePermission.role == role,
                RolePermission.doctype == doctype,
                RolePermission.company_id.is_(None),
            )
        )
        if perm is None:
            perm = RolePermission(role=role, doctype=doctype)
            db.add(perm)
        for action in actions:
            setattr(perm, f"can_{action}", True)
    await db.flush()


async def seed_admin(db: AsyncSession, email: str, password: str) -> None:
    user = await db.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        user = User(
            email=email.lower(),
            first_name="Administrator",
            hashed_password=hash_password(password),
        )
        db.add(user)
        await db.flush()
        db.add(UserRole(user_id=user.id, role="System Manager", company_id=None))
        print(f"Created admin user {email}")
    else:
        print(f"Admin user {email} already exists — skipped")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-email", default=os.environ.get("ADMIN_EMAIL"))
    parser.add_argument("--admin-password", default=os.environ.get("ADMIN_PASSWORD"))
    args = parser.parse_args()

    async with async_session_factory() as db:
        await seed_masters(db)
        await seed_permissions(db)
        if args.admin_email and args.admin_password:
            await seed_admin(db, args.admin_email, args.admin_password)
        else:
            print("No --admin-email/--admin-password given — skipping admin creation")
        await db.commit()
    print("Seeding complete.")


if __name__ == "__main__":
    asyncio.run(main())
