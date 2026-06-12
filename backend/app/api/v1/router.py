"""Master v1 router — module routers register here as they are migrated."""

from fastapi import APIRouter

from app.api.v1 import auth
from app.api.v1.accounts import (
    journal_entries,
    masters as accounts_masters,
    payment_entries,
    purchase_invoices,
    reports as accounts_reports,
    sales_invoices,
)
from app.api.v1.core import (
    companies,
    currencies,
    naming_series,
    roles,
    system_settings,
    uoms,
    users,
    workflows,
)

api_v1_router = APIRouter()

# Module 01 — Core / Setup
api_v1_router.include_router(auth.router)
api_v1_router.include_router(companies.router)
api_v1_router.include_router(users.router)
api_v1_router.include_router(roles.router)
api_v1_router.include_router(currencies.router)
api_v1_router.include_router(uoms.router)
api_v1_router.include_router(naming_series.router)
api_v1_router.include_router(workflows.router)
api_v1_router.include_router(system_settings.router)

# Module 02 — Accounts
api_v1_router.include_router(accounts_masters.router)
api_v1_router.include_router(journal_entries.router)
api_v1_router.include_router(sales_invoices.router)
api_v1_router.include_router(purchase_invoices.router)
api_v1_router.include_router(payment_entries.router)
api_v1_router.include_router(accounts_reports.router)

# Module 03+ — registered as each module is migrated
