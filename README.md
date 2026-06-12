# OptiReach ERP

A clean re-architecture of ERPNext's business logic onto a modern stack — **FastAPI**
(async Python 3.12), **Vue 3** (Composition API + Pinia + Tailwind) and **PostgreSQL**
(UUID keys, ltree trees, row-level-security multi-tenancy). No Frappe dependency anywhere.

Migration source: [frappe/erpnext](https://github.com/frappe/erpnext) (`develop` branch),
per `erpnext_migration_prompt.md`.

## Status

| Phase | Module | Status |
|---|---|---|
| 1 | **01 — Core / Setup** (Company + COA seeding, Users, RBAC, Currencies, UOM, Naming Series, Workflows, Audit, Auth) | ✅ done |
| 2 | **02 — Accounts** (GL + double-entry trigger, Journal/Payment Entries, Sales/Purchase Invoices, Tax Categories/Templates, Budgets, Payment & Bank Reconciliation, Period Closing, 7 financial reports, invoice PDFs) | ✅ done |
| 3 | 03–05 — Stock, Buying, Selling | ⏳ next |
| 4 | 06–09 — CRM, Manufacturing, HR*, Projects | pending |
| 5 | 10–12 + SaaS layer — Assets, Quality, Support, onboarding/billing/feature flags | pending |

\* Note: the `hr` module no longer exists in erpnext `develop` (moved to the separate
`frappe/hrms` app) — Module 08 will be migrated from HRMS sources.

## Quick start (Docker)

```bash
docker compose up --build
# Frontend  http://localhost:8080
# API docs  http://localhost:8000/docs
# Login: admin@example.com / ChangeMe!123  (override via ADMIN_EMAIL / ADMIN_PASSWORD)
```

## Local development

**Backend**

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -e ".[dev]"
copy .env.example .env
docker compose up postgres redis -d
alembic upgrade head
python -m scripts.seed --admin-email admin@example.com --admin-password ChangeMe!123
uvicorn app.main:app --reload
```

**Frontend**

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api to :8000
```

**Tests**

```bash
cd backend
pytest tests/unit                                          # no DB needed
TEST_DATABASE_URL=postgresql+asyncpg://erp_owner:erp_owner_dev_pw@localhost:5432/erp_test \
  pytest tests/integration                                 # needs the compose postgres
```

## Architecture

- `backend/app/core/` — config, async DB + RLS tenant context, JWT auth, RBAC engine,
  naming-series engine, workflow state machine, notifications, scheduler, websocket
- `backend/app/{models,schemas,services,api}/` — the 4-layer rule: all business logic
  lives in services; routers stay thin; models are pure ORM
- `backend/data/coa/` — Chart of Accounts templates copied verbatim from ERPNext's
  verified charts (standard, India, UAE)
- `backend/print_formats/` — Jinja2 invoice templates rendered to PDF via WeasyPrint
  (`GET /sales-invoices/{id}/pdf`, `GET /purchase-invoices/{id}/pdf`)
- `backend/migrations/` — Alembic; one revision per module
- `frontend/src/` — Pinia stores, schema-driven `FormBuilder`, generic
  `useList`/`useDocument` composables, lazy-loaded module routes
- `frontend/public/brand/config.json` — **all** branding (name, colors, logo); zero
  hardcoded product strings in code

### Multi-tenancy

Company = tenant. The API connects as the non-owner `erp_app` role; every request sets
the transaction-local GUC `app.company_id` from the JWT, which the PostgreSQL
`company_isolation` RLS policies enforce. Services also filter by `company_id`
explicitly (defense in depth). Migrations run as `erp_owner`.

### ERPNext semantics preserved

- `docstatus` 0/1/2 (Draft/Submitted/Cancelled) on every table
- Naming series patterns (`SINV-.YYYY.-`) with atomic per-company counters
- DocType-style role permission matrix incl. `if_owner`
- Append-only audit log capturing user, company, before/after JSON and client IP
