# OptiReach Metadata Engine — Implementation Plan ("The Machine")

> **Status:** PLAN ONLY. No engine code is written yet. This document is the
> blueprint we review and agree on *before* building.
>
> **Companion docs:**
> - [`erpnext_migration_prompt.md`](erpnext_migration_prompt.md) — the overall migration spec (now machine-first).
> - **`ENGINE_GUIDE.md`** — the "how to use the machine" guide. **This file does not exist yet.**
>   It is *generated as the final step of this plan* (see §9). The exact content to write is embedded there.

---

## 0. TL;DR (plain language)

ERPNext's Selling section has ~36 screens; full ERPNext has hundreds. Today OptiReach
hand-builds each screen as ~8 files. That can never scale.

**"The machine"** is one small engine that turns a *recipe card* (a short description of a
screen — its name, its fields) into a fully working screen: the list page, the form, the
Save/Edit/Delete logic, the permissions, the naming, and the menu entry. Build the machine
once, and after that:

- **Simple screens** (Territory, Campaign, Customer Group, Sales Person, …) = write one recipe card. Minutes, not days.
- **Complicated screens** (Pricing Rules, POS till, Loyalty points) = the machine renders their *form and list*, but their *calculations* are still written by hand and plugged in through a "hook."

We already built ~70% of the machine's parts while making Customer / Quotation / Sales Order.
This plan connects them into one machine and fills the missing 30%.

---

## 1. The problem, precisely

| | Today (hand-built) | With the machine |
|---|---|---|
| Add a simple master (e.g. Territory) | new model + schema + service + API router + Pinia store + list view + form view + migration (~8 files) | 1 recipe card + 1 thin model + 1 migration + permission rows. No new router/schema/service/store/views. |
| Add 10 simple masters | ~80 files, all near-duplicates | 10 recipe cards |
| Look & feel consistency | drifts per screen (hand-coded each time) | identical everywhere (one renderer) |
| Cross-module reuse (Buying, HR, CRM masters) | re-pay the cost every module | the same machine serves all modules |

**Metadata-readiness today: 4/10.** The generic foundations exist and are good quality
([`FormBuilder.vue`](frontend/src/components/shared/FormBuilder.vue),
[`useList.ts`](frontend/src/composables/useList.ts),
[`useDocument.ts`](frontend/src/composables/useDocument.ts),
[`DataTable.vue`](frontend/src/components/shared/DataTable.vue),
[`naming.py`](backend/app/core/naming.py),
[`permissions.py`](backend/app/core/permissions.py),
[`pagination.py`](backend/app/services/pagination.py)). They are just wired **per screen**
instead of **from one registry**. This plan changes that.

---

## 2. How ERPNext / Frappe implements this (the part you asked about)

ERPNext ships ~1000 screens without hand-coding them because the framework underneath
(**Frappe**) *is* a metadata engine. Understanding it tells us exactly what to copy and what
to simplify.

### 2.1 The two tables that describe everything
- A **DocType** (e.g. "Customer", "Territory") is itself just a *row* in a table called `tabDocType`.
- Each of its **fields** is a row in `tabDocField` (which fieldtype, is it required, is it shown in the list, what does it link to, etc.).
- So "DocType" and "DocField" are *themselves ordinary DocTypes* stored in their own tables. The whole system is self-describing.

When Frappe boots, it reads this metadata and from it serves the database schema, the REST
API, the list page, and the form page for every DocType — **with no per-DocType code**.
Adding a screen = inserting metadata rows.

### 2.2 One physical table per DocType
Each DocType gets one real SQL table `tab<Name>` (e.g. `tabCustomer`). Every table
automatically gets standard columns: `name` (the primary key / document ID), `creation`,
`modified`, `modified_by`, `owner`, `docstatus`, `idx`. Each stored DocField becomes one
column, whose SQL type comes from its `fieldtype` (Data→varchar, Int→int, Currency→decimal,
Check→0/1, Date→date, Text→text, Link→varchar holding the linked record's name). `bench
migrate` diffs the metadata against the live table and runs `ALTER TABLE` — this is the
"doctype sync."

Some fieldtypes hold **no column** — Section Break, Column Break, HTML, and Table — because
they only describe *layout* or *relationships*, not data.

### 2.3 Naming (`autoname`)
Each DocType's `autoname` string decides the primary key: `field:<fieldname>` (use a field's
value), `naming_series:` (use a prefix like `SINV-.YYYY.-`), `format:` (a template), `hash`,
or `autoincrement`. Series counters live in a `tabSeries` table (`name`=prefix,
`current`=integer) and are bumped atomically. Tokens like `.YYYY.` and `.#####` expand at
insert time.

### 2.4 One generic list controller
`frappe.client.get_list` builds `SELECT <columns> FROM tab<DocType>` generically. *Which*
columns show is metadata (`DocField.in_list_view` + the DocType's `title_field`). Filters,
sort, and pagination are generic query params applied to that one table. **One list
controller serves every DocType.**

### 2.5 One generic form controller
The browser fetches a DocType's metadata (the ordered list of DocFields) and renders an
input per field *by fieldtype*: Data→text box, Select→dropdown, Link→typeahead that searches
`tab<target>`, Check→checkbox, Date→datepicker, Table→an editable grid of a child DocType.
Section/Column Breaks lay it out. Rules like `depends_on` (show field B only if A is set) are
expressions stored in metadata and evaluated in the browser. **One form controller renders
every DocType.**

### 2.6 Links & Selects
A **Select** stores its choices inline in `DocField.options` (a newline list). A **Link**
stores the *target DocType name* in `DocField.options`; from that one string the engine knows
the relationship — so the search dropdown, "fetch a field from the linked doc," and "you
can't delete this, it's linked in X" integrity checks all work generically, with no
hand-written joins.

### 2.7 Child tables (line items, tax rows)
A child DocType is flagged `istable=1`. Its rows live in their own `tab<Child>` table, but
each child row carries `parent` (the parent's ID), `parenttype`, `parentfield` (which grid it
belongs to), and `idx` (row order). The parent's Table field points at the child DocType. One
parent can own several different grids (items grid, taxes grid), and the *same* mechanism is
reused everywhere. Children are saved and loaded with the parent as one document.

### 2.8 Trees (Customer Group, Territory, Item Group…)
Tree DocTypes mix in **NestedSet**: every row has a `parent_<doctype>` edge, an `is_group`
flag, and two integers `lft`/`rgt`. Because a node's descendants are exactly the rows with
`lft > node.lft AND rgt < node.rgt`, a whole subtree is one range query — no recursion. The
same engine backs Customer Group, Territory, Sales Person, Item Group, Warehouse, Account,
and Cost Center — they differ only in metadata.

### 2.9 Permissions
Permissions are `tabDocPerm` rows — one per (role, permission level) with booleans
read/write/create/delete/submit/cancel/print/… plus `if_owner`. `frappe.has_permission()`
ORs those flags across the user's roles. "User Permissions" add row-level limits (e.g. a user
may only see Territory = "North"). All generic — no per-DocType permission code.

### 2.10 Dynamic Links (Address, Contact attach to anything)
Address and Contact own a small "links" child table whose rows store `link_doctype` +
`link_name`. So one Address can attach to a Customer, a Supplier, and a Company at once — the
target *type is data, not schema*. That's how a single Address screen serves every module
without one foreign key per parent.

> **The lesson for OptiReach:** ERPNext's "exact detailing" *is* this metadata engine. We
> don't imitate it screen-by-screen; we build a smaller version of the same engine.

---

## 3. Design decisions for OptiReach (critical analysis)

We deliberately copy Frappe's *structure* but simplify where a full clone would cost us more
than it returns. Each decision below states the choice, why, and what we rejected.

### Decision 1 — Recipe cards are **Python dataclasses in code** (not a DB table, not YAML)
- **Choice:** define each screen as a typed Python object (`DocTypeDescriptor`) in
  `backend/app/registry/descriptors.py`.
- **Why:** version-controlled (git history + code review), type-checked by the IDE, and can
  directly reference the SQLAlchemy model and Python hook functions. Loading is just an
  import.
- **Rejected — DB table like Frappe's `tabDocType`:** maximally flexible (edit screens at
  runtime) but needs a whole admin UI to edit, isn't covered by git, and complicates
  migrations. Overkill for v1.
- **Rejected — YAML/JSON files:** version-controlled but untyped (easy to typo), and can't
  reference Python models/hooks directly.
- **Future path:** because the engine exposes everything through a JSON `/meta/{doctype}`
  endpoint, we can later back descriptors with a DB table to enable runtime/low-code screen
  editing (the SaaS "custom fields" feature in the original prompt) **without changing the
  frontend**. v1 stays code-based.

### Decision 2 — **One real table per master** (not one giant JSONB table)
- **Choice:** each master gets a thin SQLAlchemy model + an Alembic migration, exactly like
  ERPNext's table-per-DocType.
- **Why:** keeps real foreign keys, typed/indexed columns, row-level-security per table, and
  clean reports/joins.
- **Rejected — single "documents" table with a JSONB blob:** zero migrations per master, but
  loses FK integrity, indexing, and makes RLS and reporting painful. Not worth it.
- **Cost accepted:** ~1 migration + ~1 thin model per new master. Small and worth it.

### Decision 3 — **Generate the Pydantic schema from the descriptor at startup**
- **Choice:** the generic router builds request/response models with
  `pydantic.create_model()` from the descriptor — **no per-master schema file.**
- **Why:** removes a whole hand-written file per master and prevents schema/descriptor drift.
- **Note:** the thin SQLAlchemy *model* stays explicit in v1 (clearer FKs/indexes/RLS and
  better Alembic autogenerate). Auto-generating the model too is a possible later step.

### Decision 4 — Trees use Postgres **`ltree`** (not nested-set `lft`/`rgt`)
- **Choice:** the generic `TreeMixin` stores a materialized path in an `ltree` column, plus a
  `parent_id` edge and `is_group`.
- **Why — critical refinement over ERPNext:** the repo **already uses `ltree`** for the Chart
  of Accounts and Cost Center trees (see [`README.md`](README.md)). Reusing it keeps one tree
  mechanism across the whole app, gives indexed subtree/ancestor lookups, and **avoids the
  concurrency hazard of nested-set** (`lft`/`rgt` need careful row-locking and can corrupt
  under parallel inserts).
- **Rejected — nested-set:** what Frappe uses, but it adds a rebalancing/locking risk we'd
  rather not own when a simpler path-based option is already in the stack.
- **Cleanup bonus:** Item Group and Warehouse currently fake trees with a bare parent FK
  ([`stock_masters.py`](backend/app/services/stock_masters.py)); they get retrofitted onto
  the real tree service.

### Decision 5 — Reuse existing engines for naming, permissions, scoping, audit
- Naming → [`naming.py`](backend/app/core/naming.py) (`get_next_name` to consume,
  `peek_next_name` to preview). Permissions → [`permissions.py`](backend/app/core/permissions.py)
  (`require_permission`). Tenant isolation → existing per-request `app.company_id` GUC + RLS,
  with the router **also** filtering `company_id` explicitly (defense in depth). Audit →
  `services/audit.py` `log_audit`. **No new versions of these.**

### Decision 6 — Complicated screens plug in via a **hook escape hatch**
- **Choice:** a descriptor may register optional callables (`validate`, `before_insert`,
  `after_submit`, …) that the generic router calls at the right moment.
- **Why:** a master that needs a real rule (e.g. "parent must be a group", Item's FIFO guard)
  registers a function instead of forking the entire CRUD stack.
- **Boundary (important):** genuinely transactional documents — Sales Invoice GL posting,
  `taxes_and_totals`, `per_billed`/`per_delivered`, the pricing engine's priority
  evaluation, POS reconciliation/merge, the loyalty ledger — **stay as bespoke services.**
  The engine renders their list/form/permissions but does **not** try to express their
  calculations in metadata. Do not over-generalize.

### Decision 7 — The sidebar/menu is **also generated from the registry**
- **Choice:** the navigation reads the registry so a new master appears in the menu from its
  recipe card (grouped like ERPNext's workspace: Setup / Items & Pricing / etc.).
- **Why:** otherwise "add a screen" still needs a manual menu edit. This closes the loop.

---

## 4. What we reuse vs. what we build

| Capability | Status | Where |
|---|---|---|
| Schema-driven form renderer | ✅ reuse (small additive change) | [`FormBuilder.vue`](frontend/src/components/shared/FormBuilder.vue) — add `link` (remote-options) + `textarea` types |
| Generic table renderer | ✅ reuse as-is | [`DataTable.vue`](frontend/src/components/shared/DataTable.vue) |
| Paginated list composable | ✅ reuse as-is | [`useList.ts`](frontend/src/composables/useList.ts) |
| Single-document CRUD composable | ✅ reuse as-is | [`useDocument.ts`](frontend/src/composables/useDocument.ts) |
| Naming series engine | ✅ reuse as-is | [`naming.py`](backend/app/core/naming.py) |
| RBAC permission engine | ✅ reuse as-is | [`permissions.py`](backend/app/core/permissions.py) |
| Pagination helper | ✅ reuse as-is | [`pagination.py`](backend/app/services/pagination.py) |
| Audit logging | ✅ reuse as-is | `services/audit.py` |
| Base columns / tenant scoping mixins | ✅ reuse as-is | [`base.py`](backend/app/models/base.py) (`DocumentMixin`, `CompanyScopedMixin`) |
| **Descriptor registry** | 🔨 build | new `backend/app/registry/descriptors.py` |
| **Generic CRUD router** | 🔨 build | new `backend/app/api/v1/registry.py` |
| **`/meta/{doctype}` endpoint** | 🔨 build | in `registry.py` |
| **Link options endpoint** | 🔨 build | in `registry.py` |
| **`TreeMixin` (ltree) + tree service + `/tree`** | 🔨 build | new `backend/app/models/tree.py`, `backend/app/services/tree.py` |
| **Dynamic-links table + attach/detach** | 🔨 build | new model + endpoint (Phase 2) |
| **Generic Vue views + catch-all routes** | 🔨 build | new `GenericListView.vue`, `GenericFormView.vue`, `TreeView.vue` |
| **Registry-driven sidebar** | 🔨 build | extend [`AppShell.vue`](frontend/src/layouts/AppShell.vue) |

---

## 5. The build, phase by phase

Each phase lists its **goal**, **tasks**, **new/changed files**, and **acceptance criteria**
(how we know it's done). Time estimates assume one developer.

### Phase 0 — Engine core (≈1–2 weeks)
**Goal:** stand up the chassis on top of the existing generic parts and prove it with one
trivial flat master.

**Tasks**
1. `backend/app/registry/descriptors.py`: define `FieldSpec` and `DocTypeDescriptor`
   dataclasses (see field reference in the embedded guide, §9) and a `REGISTRY: dict[str, DocTypeDescriptor]`.
2. `backend/app/api/v1/registry.py`:
   - `GET /registry/{doctype}` — list with `page`, `page_size`, `search`, and field filters (reuse `paginate()`).
   - `GET /registry/{doctype}/{id}`, `POST`, `PATCH`, `DELETE`.
   - Each call: resolve descriptor → `require_permission(descriptor.permission_name, action)`
     → go through `get_tenant_db` and filter `company_id` when `descriptor.scoped` → set
     `owner`/`modified_by` → call `get_next_name` when `naming == "series"` → `log_audit`.
   - Build request/response Pydantic models from the descriptor with `create_model()` at startup.
3. `GET /meta/{doctype}`: return the descriptor as JSON in the exact shapes the frontend
   already consumes — `fields` → `FieldConfig[]` (keys `name/label/type/required/options/span/help`),
   `list_fields` → `Column[]`.
4. Frontend: `GenericListView.vue` + `GenericFormView.vue` reading a `:doctype` route param,
   fetching `/meta/{doctype}` once, then driving `useList`/`useDocument` against
   `/registry/{doctype}` and rendering with the unchanged `DataTable`/`FormBuilder`.
5. `router/index.ts`: add catch-all routes `/m/:doctype` and `/m/:doctype/:id`.
6. Mount the registry router once in [`router.py`](backend/app/api/v1/router.py).
7. **Pilot:** ship **Campaign** (pure flat master) end-to-end as the smoke test.

**Acceptance criteria**
- Creating, listing, editing, and deleting a Campaign works in the UI with **zero
  Campaign-specific router/schema/service/store/view files** — only a descriptor + thin model + migration + permission rows.
- `GET /meta/campaign` returns valid `FieldConfig[]`.
- Permissions enforced (a role without `create` gets 403).
- Tenant isolation verified (company A cannot see company B's Campaigns).
- **Drift test** passes: a unit test introspects each descriptor's bound model and asserts
  every non-layout `FieldSpec` maps to a real column and vice-versa.

### Phase 1 — Trees + Links (≈1 week)
**Goal:** add the two capabilities the simple Selling masters need beyond flat CRUD.

**Tasks**
1. `TreeMixin` (ltree path + `parent_id` + `is_group`) and a generic tree service
   (insert/move/rebuild path, block children under non-groups, block deleting non-leaves).
2. `GET /registry/{doctype}/tree` returning the nested structure; reparent goes through the
   tree service, never a raw `PATCH`.
3. `GET /registry/{doctype}/options?q=` for Link typeahead (maps OptiReach UUID FK ↔ human
   `title_field`).
4. `FormBuilder.vue`: additive `link` type (calls the options endpoint) + `textarea` type.
5. `TreeView.vue` for `is_tree` descriptors.
6. Retrofit Item Group and Warehouse onto the real tree service.
7. Ship **Territory, Customer Group, Sales Person** as descriptors.

**Acceptance criteria**
- A Territory tree renders, expands, and reparents correctly; deleting a non-leaf is blocked.
- A Link field on a form shows a working typeahead populated from the target master.
- Item Group / Warehouse still pass their existing tests after the retrofit.

### Phase 2 — Harvest the simple-master long tail (≈1 week)
**Goal:** close the breadth gap cheaply for everything that's config-only.

**Tasks**
1. Descriptors for **Sales Partner, Monthly Distribution, Terms Template, UTM Source** (flat masters).
2. **Tax Template** as config-plus-validation (simple master + child tax rows + a `validate` hook; reuse the accounts `TaxTemplate`).
3. **Item Price / Price List** validation hooks (unique constraint, rate > 0) via the hook escape hatch.
4. **Dynamic-links table** + generic attach/detach + **Address** and **Contact** masters attachable to Customer/Supplier.
5. Registry-driven sidebar groups (Setup / Items & Pricing) so the new masters appear in nav automatically.

**Acceptance criteria**
- Every config-only Selling Setup master from the gap table is creatable in the UI.
- An Address can be attached to both a Customer and a Supplier and listed from either.

### Phase 3 — Bespoke Selling transactions (≈2–3 weeks)
**Goal:** the genuinely hard, non-metadata logic — written by hand, surfaced through the engine.

**Tasks**
1. **Pricing engine:** Pricing Rule, Promotional Scheme, Coupon Code, Blanket Order, Shipping
   Rule, Product Bundle as bespoke services with priority evaluation, wired into Sales
   Order/Invoice line validation via hooks.
2. Confirm Sales Invoice GL posting / `taxes_and_totals` / `per_billed`-`per_delivered`
   coverage and the conversion flows (Quotation→SO→DN→SI).

**Acceptance criteria**
- A Pricing Rule discount applies correctly on a Sales Order line by priority.
- A Product Bundle explodes into component lines at billing.

### Phase 4 — POS + Loyalty — ❌ DE-SCOPED (2026-06-14)

**Decision:** POS (POS Profile/Settings, POS Invoice, Opening/Closing Entry, Invoice Merge
Log) and Loyalty (Loyalty Program, Loyalty Point Entry) are **out of scope** for OptiReach.
They are not built. If POS becomes a business requirement later, revive this phase — it is a
~3–4 week bespoke offline-capable subsystem (till sessions, cash reconciliation, invoice-merge
GL, append-only points ledger) and does not block any other phase.

### Phase 5 — Roll the engine across other modules (ongoing)
**Goal:** amortize the machine — harvest masters in Buying / HR / CRM the same way; then add
field-level permissions and workflow-engine integration into the generic router.

---

## 6. Testing & quality gates

- **Drift test** (Phase 0, ongoing): descriptor ↔ model consistency. The single most
  important safeguard against re-introducing hand-coding.
- **Per-master smoke test:** a parametrized integration test that, for each registered
  descriptor, exercises create→list→get→update→delete through the generic router.
- **Tenant-isolation test:** cross-company read/write is blocked for every scoped descriptor.
- **Tree-integrity test:** insert/move/delete maintain a valid `ltree` path; non-group nodes
  reject children.
- **Permission test:** each action is gated by `require_permission`.
- All new code follows the repo's existing rules (async everywhere, type hints, structured
  logging, no Frappe imports).

---

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| **Descriptor drift** (model/schema disagree with the recipe card) | Descriptor is the single source of truth; generate the Pydantic schema from it; the drift test fails the build on mismatch. |
| **Tenant leakage** via the generic router | Router goes through `get_tenant_db` **and** filters `company_id` explicitly; the `scoped` flag must correctly separate global masters (UOM, Currency, UTM Source) from company-scoped ones. |
| **Naming peek-vs-consume** (orphan counters) | Only `POST` calls `get_next_name`; previews use `peek_next_name`; `field:`-named masters skip the series path entirely. |
| **Over-generalizing transactions** | Hard boundary: transactions stay bespoke behind hooks; the generic child-grid handler is only for simple value grids. |
| **Link integrity / dynamic links** | Postgres FK `ON DELETE RESTRICT` + friendly "referenced by X" error translation; dynamic links have no FK, so cascade cleanup is enforced in app code. |
| **Permission granularity** (doctype-level only today) | Honor `if_owner` now; defer field-level permissions to Phase 5 as a conscious, documented gap. |
| **Perceived stall** (Phases 0–1 ship no new transaction) | Ship the Campaign pilot at the end of Phase 0 to demonstrate the payoff to stakeholders. |
| **Tree concurrency** | `ltree` path updates serialized in the tree service; provide a `rebuild` repair routine. |

---

## 8. How this changes the migration going forward

After the engine exists, the [`erpnext_migration_prompt.md`](erpnext_migration_prompt.md)
workflow changes from "hand-code 8 layers per DocType" to a **classify-first decision tree**
(those edits are made as part of this planning step):

1. For each DocType in a module, classify it:
   - **Simple master** (no logic) → write a recipe card. Done.
   - **Master + one rule** → recipe card + a `validate` hook.
   - **Transaction / heavy logic** → bespoke service (as before), but its list/form/permissions still come from a recipe card.
2. Only the third bucket is real engineering. Buckets 1–2 are config.

This is why the engine pays for itself across **every** remaining module, not just Selling.

---

## 9. FINAL STEP — generate `ENGINE_GUIDE.md`

> **Instruction (do this only after Phases 0–2 pass their acceptance criteria):**
> Create a new file `ENGINE_GUIDE.md` at the repo root with **exactly** the content in the
> block below. (It documents the machine as actually built; if any names changed during
> implementation, update them here to match the real code before saving.) Then add a one-line
> link to it from [`README.md`](README.md) under "Architecture."

~~~~markdown
# Using the OptiReach Metadata Engine ("The Machine")

This guide explains how to add new screens to OptiReach ERP without hand-coding them.
It has two parts: a **friendly walkthrough** (start here) and a **developer reference**.

---

## Part 1 — Friendly walkthrough

### What the engine is
Most ERP screens are just "fill in some boxes and Save." The engine turns a short
description of a screen — a **recipe card** — into a fully working screen: the list page, the
form, Save/Edit/Delete, permissions, naming, and the menu entry. You write the recipe card;
the engine does the rest.

There are three kinds of screens:
1. **Simple** (Territory, Campaign, Customer Group…) — just boxes. The engine does 100%.
2. **Simple + one rule** (e.g. "the parent must be a group") — recipe card + a small rule function.
3. **Complicated** (Pricing, POS, Loyalty) — real calculations, written by hand and plugged in.

### How to add a simple screen (the 5 steps)
Example: adding a "Campaign" screen.

1. **Make the database table.** Create an Alembic migration for a `campaigns` table with the
   standard document columns + your fields (e.g. `campaign_name`, `status`, `disabled`).
2. **Add a thin model.** In the right module file (e.g. `models/selling.py`), add a small
   `Campaign(Base, DocumentMixin, CompanyScopedMixin)` class matching the table.
3. **Write the recipe card.** Add one `DocTypeDescriptor` to
   `backend/app/registry/descriptors.py` (name, fields, which columns show in the list, how
   it's named). This is the only "thinking" step.
4. **Give permissions.** Insert role-permission rows so the right roles can read/write it.
5. **Add a menu link** pointing at `/m/campaign` (or let the registry-driven sidebar pick it
   up automatically).

That's it — **no new API router, schema, service, store, list page, or form page.** Open
`/m/campaign` and the screen works.

### How to add a tree screen (Territory, Customer Group…)
Same 5 steps, with two differences:
- In step 2, the model also inherits `TreeMixin` (it adds the parent/`is_group`/path columns).
- In step 3, set `is_tree=True` and `parent_field="parent_<name>_id"` on the recipe card.
The engine then shows a tree view with expand/collapse and drag-to-reparent.

### How to add a screen that needs a special rule
Write a small Python function and attach it to the recipe card's `hooks` (e.g.
`hooks={"validate": ensure_parent_is_group}`). The engine calls it at the right moment
(before saving, before submitting, etc.). Use this for one-off rules — not for big
calculations.

### When NOT to use the engine
If a screen does real accounting or inventory math — posts to the general ledger, calculates
taxes/totals, moves stock, runs pricing priority, reconciles a POS till — it stays a
hand-written service (like Sales Invoice today). The engine still renders its **form, list,
and permissions** from a recipe card, but the calculations live in code. If you're unsure,
ask: "does saving this row change a balance somewhere?" If yes → bespoke service.

---

## Part 2 — Developer reference

### The recipe card: `DocTypeDescriptor`
```python
@dataclass(frozen=True)
class FieldSpec:
    name: str                      # column / json key
    label: str                     # shown in the form
    fieldtype: str                 # see mapping table below
    options: str | None = None     # for "link" → target slug; for "select" → newline choices
    required: bool = False
    in_list: bool = False          # show as a column on the list page
    span: int = 1                  # form grid width (1 or 2)
    depends_on: str | None = None  # show only if expression is truthy
    unique: bool = False
    help: str | None = None

@dataclass(frozen=True)
class DocTypeDescriptor:
    name: str                      # human name, e.g. "Territory"
    slug: str                      # url/key, e.g. "territory"
    model: type                    # the bound SQLAlchemy model
    title_field: str               # the field used as the label in links/lists
    fields: list[FieldSpec]
    list_fields: list[str]         # which fields are list columns
    permission_name: str           # the doctype string used by require_permission()
    naming: str = "field:name"     # "field:<f>" | "series:<PATTERN>"
    scoped: bool = True            # company-scoped? False for global masters
    is_tree: bool = False
    parent_field: str | None = None
    children: list["ChildSpec"] | None = None
    hooks: dict[str, Callable] | None = None   # "validate" | "before_insert" | "after_submit" | ...
```

### fieldtype → column / UI mapping
| fieldtype | SQL column | FormBuilder control |
|---|---|---|
| `Data` | `varchar(140)` | text |
| `Text` | `text` | textarea |
| `Int` | `integer` | number |
| `Float` / `Currency` | `numeric(21,6)` | number |
| `Check` | `boolean` | checkbox |
| `Date` | `date` | date |
| `Select` | `varchar` | dropdown (choices from `options`) |
| `Link` | `uuid` FK | typeahead (options from the target's `/options` endpoint) |
| `Section Break` / `Column Break` | — (layout only) | layout |

### Endpoints the engine exposes (generic, per doctype)
| Method & path | Purpose |
|---|---|
| `GET /registry/{doctype}` | list (`page`, `page_size`, `search`, field filters) |
| `GET /registry/{doctype}/{id}` | fetch one |
| `POST /registry/{doctype}` | create (consumes naming series) |
| `PATCH /registry/{doctype}/{id}` | update |
| `DELETE /registry/{doctype}/{id}` | delete |
| `GET /registry/{doctype}/options?q=` | Link typeahead → `[{value, label}]` |
| `GET /registry/{doctype}/tree` | nested structure (tree descriptors only) |
| `GET /meta/{doctype}` | the recipe card as JSON for the frontend |

### Hook signatures
```python
def validate(db, descriptor, data: dict, existing: object | None) -> None:
    """Raise an HTTPException to block the save; mutate `data` to adjust it."""
```
Supported keys: `before_insert`, `validate`, `after_insert`, `before_update`, `after_update`,
`before_delete`, `after_submit`. Heavy logic belongs in a bespoke service, not a hook.

### Naming
- `naming="field:territory_name"` → the field's value is the ID (no counter).
- `naming="series:TERR-.YYYY.-"` → atomic per-company counter via `get_next_name`. The form
  preview uses `peek_next_name` (does not consume).

### Permissions
Seed `role_permission` rows for the descriptor's `permission_name`. The generic router calls
`require_permission(permission_name, action)` for every operation. `if_owner` is honored;
field-level permissions are not yet supported.

### Scoping
- `scoped=True` (default): the row carries `company_id`; the router filters by the current
  tenant and RLS enforces isolation.
- `scoped=False`: a global master (e.g. UOM, Currency). No `company_id`; do **not** set this
  on tenant data.

### The drift test
`tests/unit/test_descriptor_drift.py` asserts every descriptor's non-layout `FieldSpec` maps
to a real model column (and flags model columns missing from the descriptor). If it fails,
the recipe card and the table disagree — fix one of them. Keep this green.

### Checklist: shipping a new master
- [ ] Alembic migration for the table (+ RLS policy if `scoped`)
- [ ] Thin SQLAlchemy model (`+ TreeMixin` if a tree)
- [ ] One `DocTypeDescriptor` in `registry/descriptors.py`
- [ ] `role_permission` seed rows
- [ ] Menu/sidebar entry (or registry-driven nav)
- [ ] Drift test green; smoke test passes
~~~~

---

## Appendix — glossary (plain language)

| Term | Plain meaning |
|---|---|
| **DocType / doctype** | One kind of screen/record (Customer, Territory…). |
| **Descriptor / recipe card** | The short description that tells the machine how to build a screen. |
| **Master** | A simple reference record you set up once (Territory, Campaign), as opposed to a transaction. |
| **Transaction** | A document that changes balances/stock (Invoice, Stock Entry) — needs real logic. |
| **Hook** | A small custom rule function plugged into the generic flow. |
| **Tree** | A screen whose records nest under parents (Territory → USA → Texas). |
| **Scoped / multi-tenant** | The record belongs to one company; other companies can't see it. |
| **Naming series** | The auto-generated ID pattern, e.g. `SINV-2026-00001`. |
| **Drift** | When the recipe card and the database table fall out of sync (we test against this). |
