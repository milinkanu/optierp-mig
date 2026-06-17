# Using the OptiReach Metadata Engine ("The Machine")

How to add new screens (DocTypes) to OptiReach ERP without hand-coding them.
Two parts: a **friendly walkthrough** (start here) and a **developer reference**.

> Status: the engine ships **simple masters** (flat + tree), **Link** fields (to engine masters
> *and* core doctypes like Customer/Supplier), and full CRUD incl. a Delete button. Address &
> Contact are engine-served via direct party links. Transactional documents (invoices, orders,
> stock) remain bespoke services; **child grids** (line-item tables) and **polymorphic dynamic
> links** (one Address → many parents) are not yet engine-served — see "When NOT to use the engine".

---

## Part 1 — Friendly walkthrough

### What the engine is
Most ERP screens are "fill in some boxes and Save." The engine turns a short description of a
screen — a **recipe card** (`DocTypeDescriptor`) — into a working screen: the list page, the
form, Save/Edit/Delete, permissions, naming, and the sidebar entry. You write the recipe card;
the engine does the rest.

Three kinds of screens:
1. **Simple** (Campaign, Sales Partner, UTM Source…) — just fields. The engine does 100%.
2. **Tree** (Territory, Customer Group, Sales Person) — records nest under parents.
3. **Simple + one rule** — a recipe card plus a small hook function.

### How to add a simple screen (5 steps)
Example: a "Campaign" screen (already shipped — use it as the template).

1. **Make the table.** Add an Alembic migration in `backend/migrations/versions/` creating a
   `campaigns` table with the standard document columns + your fields. (Keep the revision id
   ≤ 32 chars — Alembic's `version_num` column is `varchar(32)`.)
2. **Add a thin model.** In `backend/app/models/selling.py` (or the right module), add
   `class Campaign(Base, DocumentMixin, CompanyScopedMixin)` matching the table.
3. **Write the recipe card.** Add one `DocTypeDescriptor` to
   `backend/app/registry/descriptors.py` — name, slug, model, fields, list columns, naming,
   `permissions`, `group`. This is the only "thinking" step.
4. **Seed permissions.** Run `python -m scripts.seed ...` — it reads `descriptor.permissions`
   and creates the `RolePermission` rows. (System Managers can use it immediately regardless.)
5. **Done.** The sidebar entry appears automatically (the nav reads `/meta`), and the screen
   lives at `/m/<slug>`.

No new API router, schema, service, store, list page, or form page.

### How to add a tree screen (Territory, Customer Group…)
Same 5 steps, two differences:
- In step 2 the model also inherits `TreeMixin` (adds `is_group` + the ltree `path` column),
  and you declare the self-referential parent FK (e.g. `parent_territory_id`).
- In step 3 set `is_tree=True` and `parent_field="parent_<name>_id"`.

The engine then shows a tree view, maintains the `path` automatically, and **reparents** a node
when you change its parent in the form (it cascades the path to all descendants). Deleting a
node that still has children is blocked.

### How to add a Link (dropdown to another screen)
Add a field with `fieldtype="Link"` and `options="<target-slug>"`. The form turns it into a
dropdown populated from the target. The target can be another engine master (e.g. Territory's
`parent_territory_id` → `territory`) **or** a core doctype registered in `LINK_SOURCES`
(e.g. Address's `customer_id` → `customer`). To allow a new core target, add it to
`LINK_SOURCES` in `descriptors.py` as `slug: (Model, "title_field", "PermissionName")`.

### How to add a one-off rule
Write a small async function and attach it to the recipe card's `hooks`, e.g.
`hooks={"validate": ensure_something}`. The engine calls it at the right moment. Use this for
small rules — not for big calculations.

### When NOT to use the engine
If saving a record runs real logic — posts to the general ledger, computes taxes/totals, moves
stock, evaluates pricing, reconciles a till — it stays a hand-written service (like Sales
Invoice). The engine still renders its form/list/permissions from a recipe card, but the
calculations live in code. Not yet engine-served: **child grids** (line-item tables) and
**polymorphic dynamic links** (one Address attached to many parents at once) — build those
bespoke for now. (Address/Contact today use simple direct party links, which the engine handles.)

---

## Part 2 — Developer reference

### The recipe card (`backend/app/registry/base.py`)
```python
@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    fieldtype: str                 # Data|Text|Email|Int|Float|Currency|Check|Date|Select|Link
    options: str | None = None     # Link -> target slug; Select -> newline-separated choices
    required: bool = False
    in_list: bool = False
    span: int = 1                  # form grid width (1 or 2)
    depends_on: str | None = None
    unique: bool = False
    read_only: bool = False
    help: str | None = None

@dataclass(frozen=True)
class DocTypeDescriptor:
    name: str
    slug: str                      # url/key, e.g. "customer-group"
    model: type                    # the bound SQLAlchemy model
    title_field: str               # label used in lists, links, tree nodes
    fields: Sequence[FieldSpec]
    list_fields: Sequence[str]
    permission_name: str           # doctype string used by require_permission()
    naming: str = "field:name"     # "field:<fieldname>" | "series:<PATTERN>"
    scoped: bool = True            # company-scoped? False for global masters
    is_tree: bool = False
    parent_field: str | None = None
    children: Sequence[ChildSpec] = ()       # reserved (child grids not engine-served yet)
    hooks: Mapping[str, Callable] = {}        # event -> async callable
    permissions: Mapping[str, Sequence[str]] = {}  # role -> actions (seeded by scripts.seed)
    group: str = "Setup"           # sidebar group label
```
Register it with `register(DocTypeDescriptor(...))` in `descriptors.py`.

### fieldtype → column / control
| fieldtype | SQL column | form control |
|---|---|---|
| `Data` | `varchar(140)` | text |
| `Text` | `text` | textarea |
| `Email` | `varchar` | email |
| `Int` | `integer` | number |
| `Float` / `Currency` | `numeric` | number |
| `Check` | `boolean` | checkbox |
| `Date` | `date` | date |
| `Select` | `varchar` | dropdown (choices from `options`) |
| `Link` | `uuid` FK | dropdown (options from the target's `/options`) |

### Endpoints (generic, per DocType)
| Method & path | Purpose |
|---|---|
| `GET /meta` | registry catalog the user may read (drives the sidebar) |
| `GET /meta/{doctype}` | the recipe card as JSON (fields + list columns + flags) |
| `GET /registry/{doctype}` | list (`page`, `page_size`, `search`, field filters) |
| `GET /registry/{doctype}/{id}` | fetch one |
| `POST /registry/{doctype}` | create |
| `PATCH /registry/{doctype}/{id}` | update |
| `DELETE /registry/{doctype}/{id}` | delete |
| `GET /registry/{doctype}/options?q=` | Link dropdown options `[{value, label}]` |
| `GET /registry/{doctype}/tree` | nested tree (tree DocTypes only) |

### Hooks
Signature: `async def hook(db, descriptor, obj, user) -> None` (raise an `AppError` subclass to
block; mutate `obj` to adjust). Wired events: `before_insert` and `validate` (on create),
`before_update` and `validate` (on update), `before_delete` (on delete). Heavy logic belongs in
a bespoke service, not a hook.

### Naming
- `naming="field:<f>"` → the field value is the identity (no counter); no `name` column needed.
- `naming="series:CUST-.YYYY.-"` → atomic per-company counter via `app.core.naming.get_next_name`
  (requires a `name` column on the model).

### Permissions & scoping
- The generic router calls `require_permission(permission_name, action)` on every operation;
  `descriptor.permissions` (role → actions) is seeded as `RolePermission` rows by `scripts.seed`.
- `scoped=True` (default): rows carry `company_id`; the router filters by the tenant and RLS
  enforces isolation. `scoped=False` for global masters (no `company_id`).

### Trees
Tree models use `TreeMixin` (ltree `path` + `is_group`) and a self-referential parent FK. The
path is maintained by `app/services/tree.py` on create and on reparent/rename (cascading to
descendants); non-leaf deletes are blocked. Consistent with the Chart of Accounts tree.

### The drift test (keep it green)
`backend/tests/unit/test_descriptor_drift.py` asserts every descriptor agrees with its model
(title field, persisted fields, list columns, `company_id` when scoped, `name` when series,
`parent_field` when a tree). If it fails, the recipe card and the table have drifted — fix one.

### Checklist: shipping a new master
- [ ] Alembic migration (revision id ≤ 32 chars; + RLS policy if `scoped`; + GiST path index if tree)
- [ ] Thin SQLAlchemy model (`+ TreeMixin` if a tree)
- [ ] One `DocTypeDescriptor` in `registry/descriptors.py` (with `permissions` + `group`)
- [ ] `python -m scripts.seed` to seed permissions
- [ ] `pytest tests/unit` (drift test green) — sidebar entry + `/m/<slug>` appear automatically
