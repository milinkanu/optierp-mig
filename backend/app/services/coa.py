"""Chart of Accounts seeding from ERPNext's verified COA templates.

Templates live in ``backend/data/coa/*.json`` in ERPNext's tree format:
node keys that map to dicts are child accounts; scalar keys
(``account_type``, ``account_number``, ``is_group``, ``root_type``,
``account_category``, ``tax_rate``) are properties of the node itself.

MANUAL_REVIEW: COA country templates — standard (used for USA/UK and as the
fallback), India and UAE are bundled. Other countries need template files
added to data/coa/ (copy from erpnext verified charts).
"""

import json
import re
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.accounts import ROOT_TYPE_REPORT, Account
from app.models.core import Company

COA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "coa"

_META_KEYS = {"account_type", "account_number", "is_group", "root_type", "account_category", "tax_rate"}

# Root node name -> root type, for templates that omit an explicit root_type
_ROOT_NAME_MAP = {
    "application of funds (assets)": "Asset",
    "assets": "Asset",
    "source of funds (liabilities)": "Liability",
    "liabilities": "Liability",
    "equity": "Equity",
    "income": "Income",
    "expenses": "Expense",
    "expense": "Expense",
}

# Country code -> default template key (Section 3, Module 01 assumption)
COUNTRY_TEMPLATE_MAP = {
    "IN": "in_standard",
    "AE": "ae_uae_standard",
    "US": "standard",
    "GB": "standard",
}


def available_templates() -> list[str]:
    return sorted(p.stem for p in COA_DIR.glob("*.json"))


def load_template(template_key: str) -> dict[str, Any]:
    path = COA_DIR / f"{template_key}.json"
    if not path.exists():
        raise NotFoundError(f"Chart of Accounts template '{template_key}' not found")
    return json.loads(path.read_text(encoding="utf-8"))


def template_for_country(country_code: str | None) -> str:
    return COUNTRY_TEMPLATE_MAP.get((country_code or "").upper(), "standard")


def _slugify(label: str) -> str:
    """ltree-safe label: lowercase alphanumerics and underscores."""
    slug = re.sub(r"[^a-z0-9_]+", "_", label.lower()).strip("_")
    return slug or "node"


def _node_root_type(name: str, node: dict[str, Any]) -> str:
    if "root_type" in node:
        return str(node["root_type"])
    mapped = _ROOT_NAME_MAP.get(name.lower())
    if mapped is None:
        raise ValueError(f"Cannot infer root_type for COA root '{name}'")
    return mapped


async def seed_chart_of_accounts(
    db: AsyncSession, company: Company, template_key: str
) -> dict[str, Account]:
    """Create the full account tree for a company from a template.

    Returns a map of account_name -> Account for default-account resolution.
    Assumes the RLS context is already set to ``company.id``.
    """
    template = load_template(template_key)
    tree: dict[str, Any] = template["tree"]
    created: dict[str, Account] = {}

    def walk(
        name: str,
        node: dict[str, Any],
        parent: Account | None,
        root_type: str,
        parent_path: str,
    ) -> None:
        children = {k: v for k, v in node.items() if isinstance(v, dict) and k not in _META_KEYS}
        is_group = bool(node.get("is_group")) or bool(children)
        path = f"{parent_path}.{_slugify(name)}" if parent_path else _slugify(name)
        account = Account(
            id=uuid.uuid4(),
            company_id=company.id,
            account_name=name,
            account_number=str(node["account_number"]) if node.get("account_number") else None,
            parent_account_id=parent.id if parent else None,
            root_type=root_type,
            report_type=ROOT_TYPE_REPORT[root_type],
            account_type=node.get("account_type"),
            account_category=node.get("account_category"),
            is_group=is_group,
            account_currency=company.default_currency,
            path=path,
        )
        db.add(account)
        # last-one-wins for duplicate names across branches; defaults below
        # look up well-known unique leaves (Debtors, Creditors, Cash, ...)
        created[name] = account
        for child_name, child_node in children.items():
            walk(child_name, child_node, account, root_type, path)

    for root_name, root_node in tree.items():
        if not isinstance(root_node, dict):
            continue
        walk(root_name, root_node, None, _node_root_type(root_name, root_node), "")

    await db.flush()
    return created


def _find(created: dict[str, Account], *, account_type: str | None = None, name: str | None = None) -> uuid.UUID | None:
    """Locate a default account by exact name, else by account_type (leaf first)."""
    if name and name in created:
        return created[name].id
    if account_type:
        leaves = [a for a in created.values() if a.account_type == account_type and not a.is_group]
        if leaves:
            return leaves[0].id
        groups = [a for a in created.values() if a.account_type == account_type]
        if groups:
            return groups[0].id
    return None


def resolve_default_accounts(company: Company, created: dict[str, Account]) -> None:
    """Set company default accounts after COA seeding.

    Mirrors erpnext setup's ``set_default_accounts`` name/type conventions.
    """
    company.default_receivable_account_id = _find(created, account_type="Receivable", name="Debtors")
    company.default_payable_account_id = _find(created, account_type="Payable", name="Creditors")
    company.default_cash_account_id = _find(created, account_type="Cash", name="Cash")
    company.default_bank_account_id = _find(created, account_type="Bank")
    company.default_income_account_id = _find(created, name="Sales")
    company.default_expense_account_id = _find(
        created, account_type="Cost of Goods Sold", name="Cost of Goods Sold"
    )
    company.round_off_account_id = _find(created, account_type="Round Off", name="Round Off")
    company.write_off_account_id = _find(created, name="Write Off")
    company.exchange_gain_loss_account_id = _find(created, name="Exchange Gain/Loss")


async def get_account_tree(db: AsyncSession, company_id: uuid.UUID) -> list[Account]:
    stmt = (
        select(Account)
        .where(Account.company_id == company_id)
        .order_by(Account.path)
    )
    return list((await db.execute(stmt)).scalars().all())
