# ERPNext → FastAPI + Vue.js + PostgreSQL Migration Prompt
### For: Claude Opus / GPT-4.5 / Frontier-class AI Agent
### Role assumed: Senior ERP Architect + Frappe Framework Expert + Full-Stack Engineer

---

## ⚠️ PREAMBLE — READ BEFORE DOING ANYTHING

You are acting as a **senior ERP migration architect** who is an expert in:
- The **Frappe Framework** internals (DocType system, hooks, controllers, ORM, permissions, workflows, print formats, report engine, scheduler)
- **ERPNext v15** codebase (all 11 core modules)
- **FastAPI** (async Python, Pydantic v2, dependency injection, background tasks)
- **Vue 3** with Composition API + Pinia + Vue Router
- **PostgreSQL** (schema design, indexing, triggers, row-level security)
- **SaaS product architecture** (multi-tenancy, white-labelling, billing hooks, role isolation)

Your task is to migrate the ERPNext open-source codebase into a **rebranded SaaS product** built on FastAPI (backend), Vue 3 (frontend), and PostgreSQL (database). This is NOT a simple port — it is a **clean re-architecture** that preserves all business logic while discarding Frappe's framework overhead and replacing it with a modern, maintainable, extensible stack.

---

## SECTION 1 — SOURCE CODEBASE ANALYSIS

### 1.1 Repository to Study

```
https://github.com/frappe/erpnext  (branch: develop)
```

Clone and deeply read the following before writing a single line of output code:

**Top-priority files (read in this order):**

1. `erpnext/modules.txt` — canonical list of all modules
2. `erpnext/hooks.py` — all event hooks, scheduled tasks, fixtures, permission queries
3. `erpnext/setup/` — company setup, defaults, initial data
4. `erpnext/controllers/` — base controllers (`accounts_controller.py`, `stock_controller.py`, `taxes_and_totals.py`, `buying_controller.py`, `selling_controller.py`)
5. `erpnext/accounts/doctype/` — every DocType under Accounts (GL Entry, Journal Entry, Sales Invoice, Purchase Invoice, Payment Entry, Chart of Accounts, Cost Center, Fiscal Year, Payment Reconciliation)
6. `erpnext/stock/doctype/` — Item, Warehouse, Stock Entry, Stock Ledger Entry, Batch, Serial No, Delivery Note, Purchase Receipt, Material Request, Stock Reconciliation
7. `erpnext/buying/doctype/` — Purchase Order, Supplier, Supplier Quotation, Request for Quotation
8. `erpnext/selling/doctype/` — Sales Order, Customer, Sales Quotation, Lead
9. `erpnext/crm/doctype/` — Lead, Opportunity, CRM Campaign, CRM Note, Activities
10. `erpnext/manufacturing/doctype/` — BOM, Work Order, Job Card, Production Plan, Operation, Routing, Workstation
11. `erpnext/hr/doctype/` — Employee, Department, Designation, Leave Allocation, Leave Application, Attendance, Payroll Entry, Salary Slip, Salary Structure, Expense Claim
12. `erpnext/projects/doctype/` — Project, Task, Timesheet, Timesheet Detail
13. `erpnext/assets/doctype/` — Asset, Asset Category, Asset Depreciation Schedule, Asset Movement
14. `erpnext/quality_management/doctype/` — Quality Inspection, Quality Goal, Quality Procedure
15. `erpnext/support/doctype/` — Issue, Service Level Agreement, Issue Priority, Issue Type

For each DocType JSON file (`<doctype_name>.json`), extract:
- All fields (fieldname, fieldtype, options/link target, reqd, in_list_view)
- Naming rules (autoname)
- Permissions (roles allowed)
- Workflows if any
- The corresponding Python controller methods (validate, before_save, on_submit, on_cancel, on_trash, and any custom whitelisted methods)

### 1.2 Key Frappe Patterns You Must Map to FastAPI Equivalents

| Frappe Concept | FastAPI Equivalent |
|---|---|
| DocType JSON schema | Pydantic BaseModel + SQLAlchemy Table |
| `frappe.get_doc()` | SQLAlchemy ORM `session.get(Model, id)` |
| `frappe.db.sql()` | SQLAlchemy `text()` or ORM query |
| `doc.validate()` hook | Pydantic validators + service-layer pre-save checks |
| `doc.on_submit()` hook | Post-create service method triggered after status change |
| `frappe.whitelist()` | FastAPI `@router.post()` endpoint |
| `frappe.has_permission()` | FastAPI dependency `require_permission(resource, action)` |
| Naming Series (e.g. `SINV-.YYYY.-`) | PostgreSQL sequence + Python format function |
| Child Table (table fieldtype) | One-to-many relationship via FK in a child table |
| `frappe.sendmail()` | Background task via FastAPI `BackgroundTasks` + SMTP/SendGrid |
| Scheduled tasks in `hooks.py` | APScheduler or Celery beat jobs |
| `frappe.publish_realtime()` | WebSocket via FastAPI + Redis Pub/Sub |
| Print Format (Jinja) | Jinja2 template rendered server-side, returned as PDF stream |
| Report (Script/Query Report) | FastAPI `/reports/{name}` endpoint returning structured JSON |
| `frappe.permissions` | Role-based access control (RBAC) table + middleware |
| Multi-company | `company_id` foreign key on every transaction table |
| `frappe.local.site` | Tenant ID injected via JWT or subdomain header |

---

## SECTION 2 — TARGET ARCHITECTURE

### 2.1 Backend: FastAPI

```
backend/
├── main.py                     # App factory, middleware, router registration
├── core/
│   ├── config.py               # Settings via pydantic-settings (env vars)
│   ├── database.py             # SQLAlchemy async engine + session factory
│   ├── security.py             # JWT auth, password hashing, token refresh
│   ├── permissions.py          # RBAC: roles, permissions, has_permission()
│   ├── naming.py               # Naming series engine (replaces Frappe autoname)
│   ├── workflow.py             # Workflow state machine engine
│   ├── notifications.py        # In-app + email notification dispatcher
│   ├── scheduler.py            # APScheduler setup + job registry
│   ├── websocket.py            # Redis-backed WebSocket manager
│   └── exceptions.py           # Custom HTTP exception classes
├── models/                     # SQLAlchemy ORM models (one file per module)
│   ├── base.py                 # BaseModel with id, creation, modified, owner, docstatus
│   ├── accounts.py
│   ├── stock.py
│   ├── buying.py
│   ├── selling.py
│   ├── crm.py
│   ├── manufacturing.py
│   ├── hr.py
│   ├── projects.py
│   ├── assets.py
│   ├── quality.py
│   └── support.py
├── schemas/                    # Pydantic request/response schemas (one file per module)
│   └── ...
├── services/                   # Business logic layer (one file per module)
│   └── ...
├── api/
│   ├── v1/
│   │   ├── router.py           # Master v1 router
│   │   ├── auth.py
│   │   ├── accounts/
│   │   ├── stock/
│   │   ├── buying/
│   │   ├── selling/
│   │   ├── crm/
│   │   ├── manufacturing/
│   │   ├── hr/
│   │   ├── projects/
│   │   ├── assets/
│   │   ├── quality/
│   │   └── support/
│   └── v2/                     # Reserved for future versioning
├── migrations/                 # Alembic migration scripts
│   └── versions/
├── reports/                    # Report definitions (Python query + Jinja template)
├── print_formats/              # Jinja2 PDF templates
├── tests/
│   ├── unit/
│   └── integration/
├── alembic.ini
├── pyproject.toml
└── Dockerfile
```

**Core implementation rules:**

1. **Every module has exactly 4 layers**: `models/` → `schemas/` → `services/` → `api/`
2. **Services hold all business logic** — no logic in routers, no logic in models
3. **All DB operations are async** using `asyncpg` + SQLAlchemy 2.0 async API
4. **JWT auth** with access token (15 min) + refresh token (7 days) stored in httpOnly cookie
5. **Multi-tenancy**: every table that belongs to a tenant has `company_id UUID NOT NULL`. Row-level security is enforced both at the PostgreSQL level (RLS policies) AND at the FastAPI service layer
6. **Docstatus pattern** preserved: `0 = Draft, 1 = Submitted, 2 = Cancelled` — matches ERPNext semantics for all transactional documents
7. **Naming Series**: implement a `naming_series` table and a Python function `get_next_name(series_pattern, company_id)` that atomically increments and formats (e.g. `SINV-2025-00001`)

### 2.2 Database: PostgreSQL

**Schema design principles:**

1. Use **UUIDs** (uuid_generate_v4) as primary keys for all tables — never serial integers for business documents
2. Every table has: `id UUID PK`, `creation TIMESTAMPTZ DEFAULT now()`, `modified TIMESTAMPTZ`, `modified_by UUID FK users`, `owner UUID FK users`, `docstatus SMALLINT DEFAULT 0`, `company_id UUID FK companies`
3. **Child tables** (e.g. Sales Invoice Items, BOM Items) have their own table with `parent_id UUID FK`, `parent_type VARCHAR`, `idx INTEGER` (sort order)
4. Use **PostgreSQL enum types** for fixed-choice fields (e.g. `stock_entry_type`, `leave_status`)
5. **Double-entry accounting**: `gl_entry` table must have a TRIGGER that validates debit = credit per voucher before insert
6. **Stock Ledger**: `stock_ledger_entry` table with `sle_id UUID`, `item_code`, `warehouse_id`, `actual_qty NUMERIC`, `qty_after_transaction NUMERIC`, `valuation_rate NUMERIC`, `stock_value NUMERIC` — uses a PostgreSQL trigger to maintain running balance
7. Use **partial indexes** on `(company_id, docstatus)` for every transactional table
8. Use **JSONB** columns for: custom fields, print format data, workflow data, attachments metadata

**Generate Alembic migrations** for every model. Each module's initial migration must be a separate revision file.

### 2.3 Frontend: Vue 3

```
frontend/
├── src/
│   ├── main.ts
│   ├── App.vue
│   ├── router/
│   │   └── index.ts            # Lazy-loaded routes per module
│   ├── stores/                 # Pinia stores (one per module + auth)
│   │   ├── auth.ts
│   │   ├── accounts.ts
│   │   └── ...
│   ├── composables/            # Reusable logic hooks
│   │   ├── useDocument.ts      # Generic CRUD for any document type
│   │   ├── useList.ts          # Paginated list with filters/sort
│   │   ├── usePermissions.ts
│   │   └── useNamingSeries.ts
│   ├── components/
│   │   ├── shared/             # Generic: DataTable, FormBuilder, StatusBadge, Timeline
│   │   └── modules/            # Module-specific components
│   ├── views/
│   │   ├── auth/
│   │   ├── dashboard/
│   │   ├── accounts/
│   │   ├── stock/
│   │   ├── buying/
│   │   ├── selling/
│   │   ├── crm/
│   │   ├── manufacturing/
│   │   ├── hr/
│   │   ├── projects/
│   │   ├── assets/
│   │   ├── quality/
│   │   └── support/
│   ├── api/                    # Typed API client (axios + interceptors)
│   │   └── client.ts
│   └── types/                  # TypeScript interfaces mirroring Pydantic schemas
├── public/
│   └── brand/                  # Logo, favicon, color tokens (white-label overrides here)
├── vite.config.ts
├── tailwind.config.ts
└── Dockerfile
```

**Frontend rules:**
1. Vue 3 Composition API only — no Options API
2. TypeScript strict mode throughout
3. Pinia for state, no Vuex
4. Tailwind CSS + shadcn/vue component library for UI
5. Every form is driven by a **schema config object** (mirrors ERPNext's form metadata) — this enables low-code form customization later
6. **Rebranding is entirely config-driven**: brand name, colors, logo, tagline all come from `/public/brand/config.json` and CSS variables — no hardcoded "ERPNext" anywhere in the codebase

---

## SECTION 3 — MODULE-BY-MODULE MIGRATION SPECIFICATION

For each module below, you must:

1. **Extract** the complete list of DocTypes from the source
2. **Design** the PostgreSQL schema (CREATE TABLE statements)
3. **Write** the SQLAlchemy models
4. **Write** the Pydantic schemas (Create, Update, Response, ListItem)
5. **Write** the service layer (all business logic, validation, side effects)
6. **Write** the FastAPI router (CRUD + all custom endpoints matching whitelisted methods in ERPNext)
7. **Write** the Vue views and Pinia store for that module
8. **Write** Alembic migration

Work through modules in this dependency order (later modules depend on earlier ones):

---

### MODULE 01 — Core / Setup

**Source path:** `erpnext/setup/`, `frappe/core/`

**DocTypes to migrate:**
- Company (with default accounts, currency, fiscal year)
- User, Role, RolePermission, UserPermission
- Currency, Currency Exchange
- Country, State
- UOM (Unit of Measure), UOM Conversion
- Letter Head, Print Settings
- System Settings, Naming Series
- Workflow, Workflow State, Workflow Action

**Key business logic:**
- On company creation: auto-create default Chart of Accounts (COA) based on country template
- Naming series engine: `get_next_name(series, company_id)` — atomic, per-company
- Permission engine: `has_permission(doctype, action, user_id, doc_id=None)` — mirrors `frappe.has_permission()`

**Assumptions to flag for manual review:**
- COA country templates: include templates for India, USA, UK, UAE. Flag others for human addition.
- Print format rendering: use WeasyPrint for PDF generation. Flag if wkhtmltopdf is preferred.

---

### MODULE 02 — Accounts (Financial Accounting)

**Source path:** `erpnext/accounts/`

**DocTypes to migrate (in order):**

*Masters:*
- Account (Chart of Accounts tree — use `ltree` extension in PostgreSQL for tree structure)
- Cost Center (tree structure)
- Fiscal Year, Fiscal Year Company
- Tax Category, Tax Template (Sales/Purchase)
- Payment Terms, Payment Terms Template
- Mode of Payment
- Bank, Bank Account

*Transactions:*
- Journal Entry (+ Journal Entry Account child)
- Payment Entry (+ Payment Entry Reference, Payment Entry Deduction children)
- Sales Invoice (+ Sales Invoice Item, Sales Invoice Payment, Advance, Tax, Timesheet children)
- Purchase Invoice (+ Purchase Invoice Item, Purchase Invoice Tax children)
- Purchase Order (+ Purchase Order Item child)
- GL Entry (immutable ledger — INSERT only, never UPDATE/DELETE)
- Payment Reconciliation
- Bank Reconciliation Statement
- Budget, Budget Account (child)

**Key business logic (all must be preserved exactly):**

1. **Double-entry enforcement**: on every GL Entry insert, validate that total debit = total credit for that voucher. Implement as a PostgreSQL TRIGGER `trg_gl_entry_balance_check`.

2. **Outstanding Amount Calculation**:
   ```
   outstanding_amount = grand_total - advance_paid - paid_amount + return_amount
   ```
   Recalculate on every Payment Entry submission.

3. **Taxes and Totals** (replicate `taxes_and_totals.py` exactly):
   - Net total = sum of (rate × qty) per line
   - Tax calculation supports: `On Net Total`, `On Previous Row Total`, `On Previous Row Amount`, `Actual` (fixed amount)
   - Grand total = net total + total taxes

4. **Debit/Credit determination**: use a lookup dict mapping account types to their normal balance side (Asset/Expense = Debit; Liability/Equity/Income = Credit).

5. **Multi-currency**: every transaction has `currency` + `conversion_rate` fields. GL entries always post in company currency. Store both transaction currency amount and base currency amount.

6. **Period Closing**: implement `period_closing_voucher` which freezes all GL entries before a given date.

7. **Reports to implement as API endpoints:**
   - Trial Balance (`/reports/trial-balance`)
   - Balance Sheet (`/reports/balance-sheet`)
   - Profit & Loss Statement (`/reports/profit-loss`)
   - General Ledger (`/reports/general-ledger`)
   - Accounts Receivable / Payable (`/reports/accounts-receivable`, `/reports/accounts-payable`)
   - Cash Flow Statement (`/reports/cash-flow`)

---

### MODULE 03 — Stock (Inventory Management)

**Source path:** `erpnext/stock/`

**DocTypes to migrate:**

*Masters:*
- Item (with Item Variant, Item Attribute, Item Default child tables)
- Item Group (tree)
- Warehouse (tree, with `is_group`, `company_id`, `warehouse_type`)
- Brand, Item Price, Price List

*Transactions:*
- Stock Entry (+ Stock Entry Detail child)
- Delivery Note (+ Delivery Note Item child)
- Purchase Receipt (+ Purchase Receipt Item child)
- Material Request (+ Material Request Item child)
- Stock Reconciliation (+ Stock Reconciliation Item child)
- Stock Ledger Entry (append-only ledger)
- Batch, Serial No
- Landed Cost Voucher
- Quality Inspection (link to Stock)

**Key business logic:**

1. **FIFO/Moving Average Valuation** — implement both methods. Default: Moving Average.
   - `valuation_rate` on SLE = `(old_stock_value + incoming_value) / (old_qty + incoming_qty)`
   - FIFO: maintain a FIFO queue per (item, warehouse) in a `fifo_queue` JSONB column on a `item_warehouse_balance` table

2. **`item_warehouse_balance` materialized view** (or a maintained table):
   ```sql
   (item_id, warehouse_id, actual_qty, reserved_qty, ordered_qty, planned_qty, valuation_rate, stock_value)
   ```
   Updated by trigger on `stock_ledger_entry` insert.

3. **Reorder Level**: scheduler job (daily) checks `item_warehouse_balance` against `reorder_level` and auto-creates Material Requests.

4. **Serial Number tracking**: on Delivery Note submission, validate that serial numbers are available and not already delivered. Mark as `delivery_document_no` on the Serial No record.

5. **Batch Expiry**: scheduler job (daily) marks batches as expired if `expiry_date < today()`.

---

### MODULE 04 — Buying (Procurement)

**Source path:** `erpnext/buying/`

**DocTypes to migrate:**
- Supplier (+ Supplier Group)
- Request for Quotation (RFQ) (+ RFQ Item, RFQ Supplier)
- Supplier Quotation (+ Supplier Quotation Item)
- Purchase Order (+ Purchase Order Item)
- Purchase Invoice (linked from Accounts module)
- Purchase Receipt (linked from Stock module)

**Key business logic:**

1. **Purchase Cycle**: Material Request → RFQ → Supplier Quotation → Purchase Order → Purchase Receipt → Purchase Invoice
2. On Purchase Order submission: create a `purchase_order_item_received` tracking record
3. `billed_amount` on PO line = sum of linked Purchase Invoice lines
4. `received_qty` on PO line = sum of linked Purchase Receipt lines
5. Auto-close PO when `received_qty >= qty` for all lines

---

### MODULE 05 — Selling (Sales)

**Source path:** `erpnext/selling/`

**DocTypes to migrate:**
- Customer (+ Customer Group, Territory, Sales Team child)
- Sales Order (+ Sales Order Item, Sales Taxes, Payment Schedule)
- Sales Invoice (linked from Accounts)
- Delivery Note (linked from Stock)
- Sales Quotation (+ Sales Quotation Item)
- Territory (tree)
- Sales Person (tree)
- Target Detail

**Key business logic:**

1. **Sales Cycle**: Lead → Opportunity → Quotation → Sales Order → Delivery Note → Sales Invoice
2. `billed_amount` and `delivered_qty` tracking per Sales Order line
3. Credit limit check on Sales Order submission: `outstanding_amount > credit_limit` → raise a warning (not hard block, configurable)
4. **Pricing Rule engine** (simplified):
   - Rules keyed by: (item_code OR item_group) + (customer OR customer_group OR territory) + date range
   - Apply discount % OR fixed rate

---

### MODULE 06 — CRM

**Source path:** `erpnext/crm/`

**DocTypes to migrate:**
- Lead (+ Lead Source, Industry Type)
- Opportunity (+ Opportunity Item, Opportunity Type)
- CRM Note, Activity
- Campaign, CRM Campaign Email Settings
- Contact, Address (shared with Buying/Selling)

**Key business logic:**

1. Lead → Opportunity conversion: copy fields, create linked Opportunity, mark Lead as `Converted`
2. Opportunity win probability field: manual entry, used in pipeline reports
3. **Pipeline Report**: `/reports/crm-pipeline` — group by stage, sum expected_value
4. Auto-assignment rules (round-robin or based on territory) — implement as a configurable assignment rule table

---

### MODULE 07 — Manufacturing

**Source path:** `erpnext/manufacturing/`

**DocTypes to migrate:**
- Item (extended with manufacturing fields — already in Stock module)
- BOM (Bill of Materials) (+ BOM Item, BOM Operation, BOM Scrap Item children)
- Work Order (+ Work Order Item, Work Order Operation children)
- Job Card (+ Job Card Item, Job Card Time Log children)
- Production Plan (+ Production Plan Item, Production Plan Material Request children)
- Operation, Routing (+ Routing Operation child)
- Workstation, Workstation Type

**Key business logic:**

1. **BOM Tree explosion**: recursive CTE in PostgreSQL to resolve multi-level BOMs
   ```sql
   WITH RECURSIVE bom_tree AS (
     SELECT bom_item.item_code, bom_item.qty, 1 as level FROM bom_item WHERE bom_id = $1
     UNION ALL
     SELECT bi.item_code, bi.qty * bt.qty, bt.level + 1
     FROM bom_item bi JOIN bom_tree bt ON bi.bom_id = (SELECT default_bom FROM item WHERE item_code = bt.item_code)
   ) SELECT * FROM bom_tree;
   ```

2. **Work Order Material Transfer**: on WO submission, create a Material Request for raw materials
3. **Job Card completion**: updates `completed_qty` on Work Order Operation; when all ops complete → WO status = `Completed`
4. **Capacity Planning**: query workstation availability vs. scheduled job card hours per day

---

### MODULE 08 — HR & Payroll

**Source path:** `erpnext/hr/`

**DocTypes to migrate:**

*Masters:*
- Employee (+ Emergency Contact, Education, Work History, Exit children)
- Department (tree), Designation, Employment Type, Branch
- Holiday List (+ Holiday child), Leave Type
- Salary Component (Earning/Deduction)
- Salary Structure (+ Salary Detail child)
- Salary Structure Assignment

*Transactions:*
- Leave Allocation, Leave Application, Leave Ledger Entry (append-only)
- Attendance, Attendance Request
- Timesheet (+ Timesheet Detail child)
- Expense Claim (+ Expense Claim Detail child)
- Payroll Entry (+ Payroll Employee Detail child)
- Salary Slip (+ Salary Detail Earnings, Deductions, Loans children)

**Key business logic:**

1. **Leave Balance calculation**:
   ```
   balance = total_allocated - total_consumed - total_expired
   ```
   Materialized in `leave_ledger_entry` (append-only, like GL Entry).

2. **Salary Slip generation**:
   - Fetch Salary Structure for employee on payroll period
   - Evaluate formula-based components (Python `eval()` with safe sandbox — use `simpleeval` library)
   - Components can reference: `base`, `H` (hours worked), `P` (present days), `A` (absent days)
   - Net Pay = sum(Earnings) - sum(Deductions)

3. **Payroll Entry** processes salary for all eligible employees in a department/branch in bulk

4. **Attendance** auto-marking: scheduler job marks absent if no attendance record by day end and employee has no approved leave

---

### MODULE 09 — Projects

**Source path:** `erpnext/projects/`

**DocTypes to migrate:**
- Project (+ Project User child)
- Task (+ Task Depends On child — for dependency graph)
- Timesheet (shared with HR)
- Issue (linked to Support module)

**Key business logic:**

1. Task dependency validation: no circular dependencies — check on save using topological sort (DFS)
2. Project `percent_complete` = avg(task completion %) weighted by estimated hours
3. Timesheet hours rolled up to Project `total_billable_amount`
4. **Gantt data endpoint**: `/projects/{id}/gantt` returns tasks with `start_date`, `end_date`, `dependencies[]` in a format compatible with DHTMLX Gantt or frappe-gantt

---

### MODULE 10 — Assets

**Source path:** `erpnext/assets/`

**DocTypes to migrate:**
- Asset (+ Asset Finance Book child for depreciation schedules)
- Asset Category (+ Asset Finance Book child for default depreciation)
- Asset Movement (transfer between locations/custodians)
- Asset Depreciation Schedule (auto-generated)
- Asset Capitalization
- Asset Repair

**Key business logic:**

1. **Depreciation Schedule generation** (Straight Line Method):
   ```python
   annual_depreciation = (asset_value - salvage_value) / useful_life_years
   monthly_depreciation = annual_depreciation / 12
   ```
   Also implement **Written Down Value (WDV)** method:
   ```python
   book_value_after_depreciation = book_value * (1 - depreciation_rate/100)
   ```

2. **Depreciation posting**: monthly scheduler job posts GL entries for all assets with pending depreciation schedules

3. Asset disposal: creates GL entry to remove asset value and record gain/loss on disposal

---

### MODULE 11 — Quality Management

**Source path:** `erpnext/quality_management/`

**DocTypes to migrate:**
- Quality Inspection (+ Quality Inspection Reading child)
- Quality Goal (+ Quality Goal Objective child)
- Quality Procedure (+ Quality Procedure Process child, sub-procedure tree)
- Quality Review, Quality Action, Quality Meeting

**Key business logic:**

1. Quality Inspection linked to: Purchase Receipt, Delivery Note, Stock Entry (configurable per Item)
2. Inspection result: `Accepted` if all readings are within min/max range; `Rejected` otherwise (auto-computed)
3. Block Delivery Note submission if linked Quality Inspection is `Rejected`

---

### MODULE 12 — Support

**Source path:** `erpnext/support/`

**DocTypes to migrate:**
- Issue (+ Issue Comment child)
- Service Level Agreement (SLA) (+ SLA Fulfilled On child, Priority + Response/Resolution time child)
- Issue Priority, Issue Type
- Warranty Claim

**Key business logic:**

1. **SLA Timer**: on Issue creation, calculate `response_by` and `resolution_by` timestamps based on SLA working hours and priority
2. SLA breach detection: scheduler job (every 15 min) checks open issues past `response_by` or `resolution_by` and marks `agreement_status = Breached`, sends notification
3. Issue auto-close: if status = `Replied` and no customer update in N days → auto-close (configurable)

---

## SECTION 4 — CROSS-CUTTING CONCERNS

### 4.1 Authentication & Multi-Tenancy

```python
# JWT payload structure
{
  "sub": "user_uuid",
  "email": "user@company.com",
  "company_id": "company_uuid",   # active company
  "roles": ["Accounts Manager", "Stock User"],
  "exp": 1234567890
}
```

- Every request injects `current_user` and `current_company` via FastAPI dependency
- PostgreSQL Row-Level Security:
  ```sql
  ALTER TABLE sales_order ENABLE ROW LEVEL SECURITY;
  CREATE POLICY company_isolation ON sales_order
    USING (company_id = current_setting('app.company_id')::uuid);
  ```
- Set `app.company_id` at session start: `SET LOCAL app.company_id = '<uuid>'`

### 4.2 Permission System

Implement a permission table matching ERPNext's DocType-level permissions:

```sql
CREATE TABLE role_permission (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  role VARCHAR(100) NOT NULL,
  doctype VARCHAR(100) NOT NULL,
  can_read BOOLEAN DEFAULT false,
  can_write BOOLEAN DEFAULT false,
  can_create BOOLEAN DEFAULT false,
  can_delete BOOLEAN DEFAULT false,
  can_submit BOOLEAN DEFAULT false,
  can_cancel BOOLEAN DEFAULT false,
  can_amend BOOLEAN DEFAULT false,
  can_print BOOLEAN DEFAULT false,
  can_email BOOLEAN DEFAULT false,
  can_report BOOLEAN DEFAULT false,
  if_owner BOOLEAN DEFAULT false,  -- permission applies only if owner
  company_id UUID REFERENCES companies(id)
);
```

FastAPI dependency:
```python
def require_permission(doctype: str, action: str):
    async def _check(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
        if not await has_permission(db, current_user, doctype, action):
            raise HTTPException(403, "Insufficient permissions")
    return _check
```

### 4.3 Workflow Engine

Implement a lightweight workflow state machine:

```python
class WorkflowEngine:
    async def apply_action(self, doc, action_name: str, user: User, db: AsyncSession):
        # 1. Get current workflow state
        # 2. Find valid transitions from current state for this action
        # 3. Check if user's role is allowed to take this action
        # 4. Apply state transition
        # 5. Log to workflow_action_master table
        # 6. Send notifications to next_action_role
```

### 4.4 Notification System

```python
# Notification triggers
- Document submitted → email to assigned user
- Workflow state changed → email to next approver role
- SLA breached → email to support manager
- Stock reorder level hit → email to purchase manager
- Leave approved/rejected → email to employee
```

Implement `NotificationTemplate` DocType and a `render_notification(template, context)` function using Jinja2.

### 4.5 Print Formats & PDF

- Each module has default print format Jinja2 templates (Sales Invoice, Purchase Order, etc.)
- FastAPI endpoint: `GET /documents/{doctype}/{id}/pdf?format={format_name}`
- Use **WeasyPrint** to convert HTML/CSS to PDF
- Templates stored in `print_formats/` directory, loaded at startup into a Jinja2 `Environment`

### 4.6 Background Jobs / Scheduler

Use **APScheduler** with PostgreSQL job store:

```python
SCHEDULED_JOBS = [
    {"func": "jobs.stock.reorder_level_check", "trigger": "cron", "hour": 6},
    {"func": "jobs.accounts.auto_post_depreciation", "trigger": "cron", "day": 1},
    {"func": "jobs.hr.mark_absent", "trigger": "cron", "hour": 23, "minute": 30},
    {"func": "jobs.support.sla_breach_check", "trigger": "interval", "minutes": 15},
    {"func": "jobs.stock.batch_expiry_check", "trigger": "cron", "hour": 1},
    {"func": "jobs.hr.send_birthday_reminders", "trigger": "cron", "hour": 8},
]
```

### 4.7 Audit Trail

Every `INSERT`, `UPDATE`, `DELETE` on transactional tables must log to:
```sql
CREATE TABLE audit_log (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  creation TIMESTAMPTZ DEFAULT now(),
  doctype VARCHAR(100),
  document_id UUID,
  action VARCHAR(20),  -- INSERT / UPDATE / DELETE / SUBMIT / CANCEL
  user_id UUID,
  company_id UUID,
  data_before JSONB,
  data_after JSONB,
  ip_address INET
);
```
Implement as a FastAPI middleware + service-layer interceptor (NOT a DB trigger, to capture user context).

---

## SECTION 5 — REBRANDING & SAAS CUSTOMIZATION

### 5.1 White-Label Configuration

All branding must be driven by `public/brand/config.json`:
```json
{
  "product_name": "YourERP",
  "tagline": "Run your business, your way",
  "logo_url": "/brand/logo.svg",
  "favicon_url": "/brand/favicon.ico",
  "primary_color": "#4F46E5",
  "secondary_color": "#7C3AED",
  "support_email": "support@yourerp.com",
  "docs_url": "https://docs.yourerp.com"
}
```

**Rules:**
- Zero occurrences of "ERPNext", "Frappe", "frappe.io" in any user-visible string
- All `© Frappe Technologies` references replaced with configurable `© {product_name}`
- Module icons, color scheme, and sidebar order all configurable

### 5.2 SaaS-Specific Features to Add (Beyond ERPNext)

These do not exist in ERPNext and must be built new:

1. **Tenant Onboarding Flow**:
   - `/onboarding` wizard: Company name → Industry → Country → Admin email → Plan selection
   - Auto-provisions: database schema, default COA, sample data (optional), first admin user

2. **Subscription & Billing Module** (new, not in ERPNext):
   - `subscription_plan` table: name, max_users, max_companies, feature_flags JSONB, price_monthly
   - `tenant_subscription` table: tenant_id, plan_id, status, trial_ends_at, next_billing_at
   - Middleware that checks `feature_flags` before allowing access to premium modules
   - Webhook endpoint for payment provider (Stripe/Razorpay) events

3. **Feature Flag System**:
   ```python
   FEATURE_FLAGS = {
     "manufacturing": True,   # included in plan
     "multi_currency": True,
     "api_access": False,     # premium feature
     "custom_reports": False,
   }
   ```
   Check in FastAPI dependency: `require_feature("manufacturing")`

4. **API Key Management** (for SaaS customers to build integrations):
   - `api_key` table: key_hash, tenant_id, scopes[], rate_limit, last_used_at
   - Rate limiting middleware using Redis

5. **Usage Analytics** (internal, not exposed to tenants):
   - Log module usage events to a `usage_event` table
   - `/admin/analytics` endpoint for internal dashboard

---

## SECTION 6 — EXECUTION PLAN & PHASING

### Phase 1 — Foundation (Week 1–2)

Deliver:
- [ ] Project scaffolding (backend + frontend directory structure)
- [ ] Core module: Company, User, Role, Permission, Naming Series
- [ ] Auth system: JWT login/logout/refresh, role assignment
- [ ] PostgreSQL setup: base models, Alembic setup, RLS policies
- [ ] Vue app shell: layout, sidebar, router, auth store
- [ ] Brand config system: logo/color injection, no ERPNext branding anywhere

### Phase 2 — Financial Core (Week 3–5)

Deliver:
- [ ] Accounts module complete (COA, GL Entry, Journal Entry, Sales Invoice, Purchase Invoice, Payment Entry)
- [ ] Double-entry validation trigger
- [ ] All 6 financial reports
- [ ] Multi-currency support
- [ ] PDF print format: Sales Invoice, Purchase Invoice

### Phase 3 — Supply Chain (Week 6–8)

Deliver:
- [ ] Stock module (Item, Warehouse, SLE, moving average valuation)
- [ ] Buying module (Supplier, RFQ, PO, Purchase Receipt)
- [ ] Selling module (Customer, Quotation, SO, Delivery Note)
- [ ] Full purchase and sales cycle end-to-end

### Phase 4 — Operations (Week 9–11)

Deliver:
- [ ] Manufacturing (BOM, Work Order, Job Card, BOM explosion)
- [ ] HR & Payroll (Employee, Leave, Attendance, Salary Slip)
- [ ] Projects (Project, Task, Timesheet, Gantt endpoint)

### Phase 5 — Supporting Modules + SaaS Layer (Week 12–14)

Deliver:
- [ ] Assets (depreciation schedule, GL posting)
- [ ] Quality Management (inspection, block on rejection)
- [ ] Support (Issue, SLA timer, breach detection)
- [ ] CRM (Lead, Opportunity, pipeline report)
- [ ] Tenant onboarding wizard
- [ ] Subscription/billing hooks
- [ ] Feature flag middleware

---

## SECTION 7 — ASSUMPTIONS & ITEMS FOR MANUAL REVIEW

The following items require human decision before implementation. Mark each as a TODO stub with a `# MANUAL_REVIEW:` comment:

| # | Item | Default Assumption | Review Needed |
|---|------|-------------------|---------------|
| 1 | PDF engine | WeasyPrint | Confirm vs. wkhtmltopdf |
| 2 | Email provider | SMTP (configurable) | Confirm vs. SendGrid/SES |
| 3 | Payment gateway | Stripe + Razorpay webhooks | Confirm which to integrate |
| 4 | Chart of Accounts templates | India, USA, UK, UAE | Add more country templates |
| 5 | Salary formula sandbox | `simpleeval` library | Security review needed |
| 6 | Multi-tenancy model | Shared DB, schema-per-tenant via RLS | Confirm vs. DB-per-tenant |
| 7 | Real-time (WebSocket) | Redis Pub/Sub | Confirm Redis availability |
| 8 | File storage | Local disk + S3-compatible | Confirm S3 bucket/provider |
| 9 | Full-text search | PostgreSQL `tsvector` | Confirm vs. Elasticsearch |
| 10 | Mobile app | Not in scope | Flag for future phase |
| 11 | Regional tax (GST/VAT) | GST (India) included | Confirm which tax regimes |
| 12 | Data migration from ERPNext | Not in scope | Define migration scripts separately |

---

## SECTION 8 — OUTPUT FORMAT INSTRUCTIONS

For each module you implement, structure your output as follows:

```
## MODULE XX — {Module Name}

### 8.1 Schema (SQL)
[CREATE TABLE statements]

### 8.2 SQLAlchemy Models
[Python code]

### 8.3 Pydantic Schemas
[Python code]

### 8.4 Service Layer
[Python code — all business logic here]

### 8.5 FastAPI Router
[Python code]

### 8.6 Alembic Migration
[Python migration script]

### 8.7 Vue Store (Pinia)
[TypeScript code]

### 8.8 Vue Views
[Vue 3 SFC — key list view + form view]

### 8.9 Assumptions Made
[Bullet list of any assumptions for this module]

### 8.10 Items Flagged for Manual Review
[Bullet list with MANUAL_REVIEW labels]
```

---

## SECTION 9 — CONSTRAINTS & QUALITY REQUIREMENTS

1. **No Frappe dependency** anywhere in the output code — zero imports of `frappe`, `erpnext`, or any Frappe library
2. **Python 3.12+** syntax throughout
3. **All async** — no synchronous DB calls in FastAPI handlers
4. **Type annotations** on every function signature (Python + TypeScript)
5. **No hardcoded secrets** — all config via environment variables read through `pydantic-settings`
6. **Tests**: write at minimum one unit test and one integration test per service module
7. **OpenAPI docs**: every endpoint must have `summary`, `description`, `response_model`, and example in the docstring
8. **Error responses**: use a uniform error envelope `{"detail": "...", "code": "ERR_CODE", "field": "..."}` for all 4xx responses
9. **CORS**: configurable allowed origins via env var `ALLOWED_ORIGINS`
10. **Logging**: structured JSON logging via `structlog`, include `trace_id` on every log line
11. **Docker**: provide `Dockerfile` for backend and frontend, and a `docker-compose.yml` for local dev with PostgreSQL + Redis

---

## BEGIN

Start with **Phase 1, Module 01 (Core/Setup)**. Follow the output format from Section 8 exactly. After completing each module, pause and ask: *"Proceed to the next module?"* before continuing, to allow for review.

For anything not specified above that you encounter in the ERPNext codebase, apply your best judgment as a senior ERP architect, document the decision inline with a comment, and flag it in the "Assumptions Made" section of that module's output.
