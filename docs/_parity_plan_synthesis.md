Confirmed all the load-bearing facts. The DeliveryNote inline columns overlap exactly as the map warns (currency, conversion_rate, total_qty, base_total, grand_total, base_grand_total — but NOT net_total/total/discount/etc.), and PurchaseInvoice has no `update_stock` column. I have enough verified ground truth to write the plan.

---

# Selling/Buying Parity — Ordered Implementation Plan

## Verification preamble (what I checked before planning)

I spot-verified the highest-risk claims in the area maps against the live code:

- **Engine already does per-line % discount.** `taxes_and_totals.py:178-187` (`calculate_item_values`) computes `rate = price_list_rate*(1 - discount_percentage/100)` and `ItemRow` (lines 56-70) already declares `price_list_rate` + `discount_percentage`. **Margin is NOT modeled** — confirmed. The map is accurate.
- **Migration head is `0023_buying_address_contact`** and the 0001→0023 chain is linear and unbroken. Every map that says "next = 0024, down_revision='0023_buying_address_contact'" is correct. **But note: there are 23 migrations and seven of them (0007–0023) are NOT the ones several maps reference for "templates."** The numbering in some maps ("0007_*" for a new buying migration) is stale — the next free number is **0024**, full stop. See *Contradictions* §C1.
- **`TotalsMixin` (accounts.py:414-453)** declares `currency, conversion_rate, total_qty, total, base_total, net_total, base_net_total, total_taxes_and_charges, base_total_taxes_and_charges, apply_discount_on, additional_discount_percentage, discount_amount, grand_total, base_grand_total, rounded_total, rounding_adjustment`.
- **`DeliveryNote` (stock.py:486-523)** inline-declares `currency, conversion_rate, total_qty, base_total, grand_total, base_grand_total` — a **partial** overlap with `TotalsMixin`. It is MISSING `total, net_total, base_net_total, total_taxes_and_charges, base_total_taxes_and_charges, apply_discount_on, additional_discount_percentage, discount_amount, rounded_total, rounding_adjustment`. The DN-depth map's column-overlap warning is accurate.
- **`PurchaseInvoice` (accounts.py:567-593)** has **no `update_stock` column**; `SalesInvoice` (accounts.py:507) does. The invoice map's asymmetry warning is correct.
- **`InvoiceItemMixin` (accounts.py:470-491)** has exactly the columns the map lists; no discount/margin/price_list_rate/conversion_factor/stock_qty. Correct.

Everything material in the maps held up. The plan below is anchored to those verified line numbers.

---

## How the tranches are ordered

Two axes drive ordering: **migration risk** (zero-migration > additive-nullable-columns > new-tables/mixin-blast) and **leverage** (shared-mixin / shared-form changes that fan out to many doctypes at once). I deliberately split the parity report's #1 (per-line discount/margin) because **the discount half is low-risk and the margin+UOM half is the single riskiest change in the whole effort**.

| Tranche | Theme | Migration profile | Risk |
|---|---|---|---|
| **0** | Zero-migration wins (masters surfacing, tax-template picker) | none | very low |
| **1** | Per-line **Discount %** (engine already supports it) | additive nullable cols on shared mixin | low–med |
| **2** | More-Info tab + A&C into DN/RFQ/SQ | additive nullable FK cols | low–med |
| **3** | Surface hidden invoice accounting fields (Group A pure UI; Group B small cols) | none → small | low → med |
| **4** | Payment Terms Template master + Payment Schedule | new child tables + mixin cols | high |
| **5** | Per-line **Margin + multi-UOM** (stock-math correctness) | additive cols, but logic-heavy | **highest** |
| **6** | Delivery Note depth + Purchase Receipt depth | new tax tables + return/totals cols | high |

---

# TRANCHE 0 — Zero-migration, high-leverage (DO FIRST)

These items add **no columns** and touch **no transactional services**. They are declarative or pure-frontend, and several unblock later tranches (e.g. the `payment-terms-template` link source is needed by Tranche 4's master and by the Customer/Supplier descriptors here).

> **Convention reminder for this whole tranche:** a field is surfaced by adding a `FieldSpec` to the descriptor; the engine auto-generates the Pydantic model (stops ignoring the field), the `/meta` JSON, and the Vue form. No DB/model/router change. Link targets must resolve via a registered descriptor OR a `LINK_SOURCES` entry, and the target needs a seeded read permission or the dropdown is silently empty.

### 0.1 — Customer & Supplier masters: surface dropped FK fields *(Priority #5)*

**Title:** Expose `tax_category_id`, `payment_terms_template_id`, `receivable/payable_account_id` on Customer & Supplier descriptors.

**Migration:** **NONE.** All four columns already exist on the models (`selling.py:52-69`, `buying.py:40-52`) with FKs and prior migrations applied. This is the canonical "no migration" item.

**Backend changes (all in `backend/app/registry/descriptors.py`):**
1. At `LINK_SOURCES` (lines 581-587) add two entries (Account already resolves via slug `account`):
   - `"tax-category": (TaxCategory, "title", "Tax Category")`
   - `"payment-terms-template": (PaymentTermsTemplate, "template_name", "Payment Terms Template")`
   - Import `TaxCategory, PaymentTermsTemplate` from `app.models.accounts`.
2. Customer descriptor (lines 307-323) — add three `FieldSpec`s near the financial fields:
   - `FieldSpec("tax_category_id", "Tax Category", "Link", options="tax-category")`
   - `FieldSpec("payment_terms_template_id", "Payment Terms", "Link", options="payment-terms-template")`
   - `FieldSpec("receivable_account_id", "Receivable Account", "Link", options="account")`
3. Supplier descriptor (lines 363-379) — mirror with `payable_account_id` instead of receivable.
4. `backend/scripts/seed.py` (near the `Tax Category` rows at 57/68): seed a **`Payment Terms Template`** `RolePermission` (read) for Sales/Purchase/Accounts roles. Without it `GenericFormView.resolveLinks` (GenericFormView.vue:40-43) swallows the 403 and the dropdown is empty (the field still saves).

**Frontend:** none — `GenericFormView` renders new Link `FieldSpec`s automatically once the slug resolves.

**Convention:** descriptor field name == model column name exactly; Link `options` = kebab-case target slug.

**Verification (Playwright):** navigate to `/m/customer/new`. Snapshot the form — the three new Link selects should render. Pick a Payment Terms Template + Tax Category + Receivable Account, save, reopen the saved record, confirm values persist. API check: `GET /api/v1/registry/customer/{id}` returns the three FK ids non-null. Repeat for `/m/supplier/new`.

**Contradiction to resolve first (C2):** there is a *second* silent-drop path — the bespoke `CustomerCreate/SupplierCreate` in `schemas/accounts.py:14-53` (the `/accounts` API, separate from the engine). Before coding, confirm which path the UI actually calls. The GenericForm uses `/registry/{slug}`; if any screen still posts to `/accounts`, those bespoke schemas also need the fields (and `create_customer/create_supplier` service). **Default assumption: engine path only — verify, don't assume.**

### 0.2 — customer_type "Partnership" parity *(from PR-depth map)*

**Title:** Add `Partnership` to Customer's `customer_type` Select.

**Migration:** **NONE** — `Customer.customer_type` is `String(20)`, permissive (selling.py:45-50). Supplier already has Partnership.

**Backend:** `descriptors.py:309` — change Select options from `"Company\nIndividual"` to `"Company\nIndividual\nPartnership"`.

**Verification:** `/m/customer/new` snapshot → customer_type dropdown shows three options; save with Partnership, confirm round-trip.

### 0.3 — Tax Category + tax-template picker on trade docs & invoices *(supporting #6/taxes)*

**Title:** Add a Tax Template (and optional Tax Category) picker to `OrderFormView` and `InvoiceFormView`.

**Migration:** **NONE.** `tax_template_id` is already accepted on every create schema (`OrderCreateBase.tax_template_id` buying.py:43; `InvoiceCreateBase.tax_template_id` accounts.py:244). Backend `_load_tax_rows` already resolves it with full precedence. **Backend needs zero changes.**

**Frontend changes:**
1. `types/accounts.ts` (after `TaxRowIn` ~line 45): add `TaxTemplate`, `TaxTemplateDetail`, `TaxCategory` interfaces; add `tax_category_id?: string|null` to `Customer`/`Supplier`.
2. `stores/accounts.ts` (mirror `accountOptions`/`fetchCustomers` at 21-48): add `taxTemplates`/`taxCategories` state, `fetchTaxTemplates(kind)` → `api.get('/tax-templates',{params:{kind}})`, `fetchTaxCategories()` → `api.get('/tax-categories')`. **Gotcha: both return bare arrays, not `ListResponse` — do NOT read `resp.data.items`.**
3. `InvoiceFormView.vue`: add `taxTemplateId` ref; fetch in the onMounted `Promise.all` (line 381); render a `<select>` just before `<TaxesCharges>` (line 628). On change, map `template.details` → `taxes.value` (`Number()` the decimal strings).
4. `OrderFormView.vue`: identical, picker before line 647, fetch in onMounted Promise.all (line 375). `kind = cfg.value.buying ? 'purchase' : 'sales'`.

**Convention / precedence decision (must pick ONE — this is contradiction C3):** backend treats inline `taxes` as **highest priority** (truthy list short-circuits before `tax_template_id`). So either:
- **(a)** picking a template **fills the rows client-side** and you **never send `tax_template_id`** (rows are authoritative, user can edit them), or
- **(b)** you send **only `tax_template_id`** and keep rows empty (server expands).

Recommend **(a)** — it matches the editable `TaxesCharges` UX and avoids the "template select looks ignored" trap. Do not do both for the same row set.

**Verification:** `/sales-orders/new`, snapshot, pick "GST 18% (CGST+SGST)" → the TaxesCharges grid auto-populates rows; save; `GET /api/v1/sales-orders/{id}` shows the expanded tax rows and recomputed `grand_total`. Network tab: confirm payload carries the populated `taxes` array (model a) and not `tax_template_id`.

---

# TRANCHE 1 — Per-line Discount % *(Priority #1, the low-risk half)*

The engine **already** computes discounted rate from `price_list_rate` + `discount_percentage`. The only gap is: columns to persist them, schema to accept/echo them, services to pass them in, and the grid/preview to show them. **I am deliberately deferring Margin and multi-UOM to Tranche 5** — they are net-new engine logic and stock-math correctness risks, and bundling them here would make a low-risk change high-risk.

### 1.1 — Add discount columns to the shared line mixin

**Title:** Add `price_list_rate`, `base_price_list_rate`, `discount_percentage`, `discount_amount` to `InvoiceItemMixin`.

**Migration:** **REQUIRED (additive, nullable-with-server-default).** New file `0024_line_discount.py`, `down_revision='0023_buying_address_contact'`.

**Backend:**
- `accounts.py:470` — add to `InvoiceItemMixin` (fans out to all 6 line tables):
  - `price_list_rate`, `base_price_list_rate` → `Numeric(21,6) default 0 server_default text("0")`
  - `discount_percentage` → `Numeric(8,4) default 0 server_default text("0")`
  - `discount_amount` → `Numeric(21,6) default 0 server_default text("0")`
- Migration `upgrade()`: `op.add_column` each on the 4 **order** tables (`quotation_items, sales_order_items, purchase_order_items, supplier_quotation_items`) **and** the 2 invoice item tables (`sales_invoice_items, purchase_invoice_items`) — because the mixin column appears on all 6, the migration must ALTER all 6 or SQLAlchemy's mapping and the DB schema diverge. `downgrade()` drops them. Reuse the `_item_row_columns()` / `_amount()` numeric style from `0005_buying.py:77-92`.

**Convention:** `Numeric(21,6)` money, `Numeric(8,4)` percent; `nullable=False, default=0, server_default=text("0")` verbatim.

### 1.2 — Engine: support absolute per-line `discount_amount`

**Title:** Extend `ItemRow` + `calculate_item_values` for absolute discount.

**Backend (`taxes_and_totals.py`):**
- `ItemRow` (56-70): add `discount_amount: Decimal = ZERO`.
- `calculate_item_values` (178-187): keep the existing `%` branch; add: if `discount_amount` set, `rate = price_list_rate - discount_amount` (when `price_list_rate` present), else fall through. Preserve the existing `%` behavior and the proportional additional-discount distribution downstream (it already passed verification).
- Add a unit test mirroring the pure-function testing convention (assert `%` and absolute paths, and that doc-level additional discount still distributes).

### 1.3 — Schemas (shared)

**Backend (`schemas/buying.py`):**
- `OrderItemIn` (19-30): add `price_list_rate: Decimal|None=None`, `discount_percentage: Decimal=0 (ge=0,le=100)`, `discount_amount: Decimal=0 (ge=0)`.
- `OrderItemResponse` (46-59): echo `price_list_rate, discount_percentage, discount_amount`.
- Selling `QuotationItemResponse/SalesOrderItemResponse` inherit automatically. For invoices, mirror in `InvoiceItemIn`/response in `schemas/accounts.py` (`InvoiceItemIn` already exists at 215).

### 1.4 — Services pass discount into the engine and persist

**Backend (`sales_order.py`, `purchase_order.py`, `quotation.py`, and SI/PI services):**
- Where `engine_items=[ItemRow(...)]` is built (e.g. sales_order.py:169), store the **resolved base** as `price_list_rate` and pass `discount_percentage=row.discount_percentage, discount_amount=row.discount_amount`. Keep existing rate-resolution (`resolve_item_rate`/`apply_selling_pricing`/blanket) to obtain the base; **let the engine derive the final `rate`** (the engine is authoritative — never hand-compute line amount in the service).
- In the `*_Item(...)` constructors (e.g. sales_order.py:234-255), persist `price_list_rate, base_price_list_rate, discount_percentage, discount_amount` from the engine item.

### 1.5 — Frontend grid + types + preview

**Frontend:**
- `types/trade.ts`: add the matching optional fields to `OrderItemIn` (5) and `OrderItemDetail` (34).
- `OrderFormView.vue` `gridColumns` (102): push `{key:'discount_percentage',label:'Discount %',type:'number',align:'right'}`. `newItemRow` (132): seed `discount_percentage:0, discount_amount:0`. `save()` already forwards whole rows; `onCell` already coerces numbers — **no extra wiring**.
- `ItemsGrid.vue` `amountOf` (58): `base = row.price_list_rate ?? row.rate; afterDisc = row.discount_amount>0 ? base-row.discount_amount : base*(1-(row.discount_percentage||0)/100); amount = qty*afterDisc`.
- `utils/totals.ts` `computeTotals` netTotal (40): apply the same per-line discount so the live preview matches the server. **Both must change together or the preview lies** (server stays authoritative on save).

**Verification:** `/sales-orders/new`, add an item, type `10` in Discount %. Snapshot: the Amount column and DocumentTotals Net Total drop by 10%. Save; `GET /api/v1/sales-orders/{id}` — line shows `discount_percentage=10`, `price_list_rate` = base, `rate` = base×0.9, and header `net_total` matches the preview. Repeat for a quotation and a purchase order.

---

# TRANCHE 2 — More-Info tab + Address & Contact into DN/RFQ/SQ *(Priorities #3 & #4)*

Additive nullable FK columns only. Two work items share one migration.

### 2.1 — Shared "More Info" tab on OrderFormView *(Priority #3)*

**Title:** Wire Campaign / Source / Territory / Customer Group / Sales Partner on Quotation + Sales Order (selling only).

**Scope decision (contradiction C4):** masters exist for Campaign, Territory, Customer Group, Sales Person, Sales Partner, UTM Source. Masters **do NOT exist** for Project, Opportunity, Sales Team — `resolve_link_source` returns None for those slugs. **Wire only the five that have masters; defer Project/Opportunity/Sales Team as a separate epic.** **Do NOT add selling fields to Purchase Order** — ERPNext PO More-Info differs; guard everything with `!cfg.buying`.

**Migration:** REQUIRED. `0025_order_more_info.py` (chains off 0024). Add nullable FKs to `quotations` + `sales_orders`: `campaign_id→campaigns.id`, `source_id→utm_sources.id`, `territory_id→territories.id`, `customer_group_id→customer_groups.id`, `sales_partner_id→sales_partners.id`, all `ondelete='SET NULL'`, `use_alter=True, name='fk_...'`.

**Backend:** add the FK columns to `Quotation`/`SalesOrder` (selling.py, mirror Customer's columns at 62-69); add optional `uuid.UUID|None=None` fields to `QuotationCreate/SalesOrderCreate` + responses (schemas/selling.py); thread into the `SalesOrder(...)`/`Quotation(...)` constructors (sales_order.py:183-218, quotation.py). Optionally default `territory_id/customer_group_id` from the resolved customer.

**Frontend (`OrderFormView.vue`):** replace the catch-all placeholder (lines 692-697 — note the curly apostrophe U+2019, so a straight-quote grep misses it) with `<div v-show="activeTab === 'More Info'">`. Render five `<select class="form-input">` link pickers (AddressContactTab pattern, lines 119-130), gated `v-if="!cfg.buying"`. Add refs (campaignId, sourceId, …), fetch masters in onMounted via `api.get('/registry/campaign',{params:{page_size:200}})` etc. In `save()` (265-311), add the ids to the **selling** branches only. Extend `OrderDetail` in trade.ts; optionally show in the summary card.

**Verification:** `/sales-orders/new` → More Info tab → snapshot shows five selects. Pick values, save, `GET /api/v1/sales-orders/{id}` returns the five ids. `/purchase-orders/new` → More Info tab → snapshot confirms those selects are **absent**.

### 2.2 — Address & Contact tab into Delivery Note + Supplier Quotation *(Priority #4)*

**Title:** Wire `AddressContactTab` into DeliveryNote and Supplier Quotation; add backing FKs.

**Migration:** REQUIRED. Same `0025` (or a sibling `0025b`). Copy `0023_buying_address_contact.py:22-41` loop. `delivery_notes`: add `customer_address_id, shipping_address_id, contact_person_id` (DN party is the customer). `supplier_quotations`: add `supplier_address_id, shipping_address_id, contact_person_id`. Keep `fk_{table}_..._address/_contact_person` naming, FK to `addresses`/`contacts`, `ondelete='SET NULL'`.

**Backend (do models/schemas/services BEFORE frontend, or POSTs error):**
- `stock.py` DeliveryNote (486): add the 3 FKs (copy PO block buying.py:228-236, renaming supplier→customer). `buying.py` SupplierQuotation (149): add the 3 (identical to PO).
- `schemas/stock.py` `DeliveryNoteCreate`(356)/`Response`(381): add the 3. `schemas/buying.py` `SupplierQuotationCreate`(205)/`Response`(220): add the 3.
- `delivery_note.py` `create_delivery_note` constructor (~74-86): set from payload. `rfq.py` `create_supplier_quotation` (~170): set from payload (mirror purchase_order.py:216-218). Loaders return full rows → responses auto-surface.

**Frontend:**
- `DeliveryNoteFormView.vue`: import `AddressContactTab`; add `addressContact` ref + `acPayload('customer')` (copy OrderFormView 156-163); replace the placeholder (246-251) with the tab block; `Object.assign(payload, acPayload('customer'))` in save() (115).
- `RfqView.vue` SQ panel (216-261): embed `<AddressContactTab v-model="sqAddressContact" :party-id="sqSupplierId" party-kind="supplier"/>` in a collapsible section (form isn't tabbed). In `saveSq()` (116) add the 3 mapped fields; reset in the success block.

**RFQ decision (contradiction C5):** RFQ has **no single party** (`rfqSupplierIds` is multi-select). `AddressContactTab`'s one-party contract does not fit. **Defer RFQ A&C** unless explicitly required; if needed later, scope it to a shipping-address-only plain `<select>`, not the shared tab. The prompt lists RFQ as a target but the data model makes full A&C on RFQ awkward — flag and confirm scope.

**Verification:** `/delivery-notes/new` → A&C tab → snapshot shows billing/shipping/contact pickers filtered to the chosen customer; save; `GET /api/v1/delivery-notes/{id}` returns `customer_address_id` etc. SQ: open the SQ create panel, snapshot the embedded A&C section, save, confirm via `GET /supplier-quotations/{id}`.

---

# TRANCHE 3 — Surface backend-hidden invoice accounting fields *(Priority #6)*

Split into **Group A (pure UI, zero migration — ship immediately)** and **Group B (small column adds + submit logic — riskier, ship after)**.

### 3.1 — Group A: Debit-To/Credit-To, per-line account, per-line cost center *(zero migration)*

**Title:** Wire the three accounting selectors that are already accepted/stored/posted.

**Migration:** **NONE.** `debit_to_id` (accounts.py:505) / `credit_to_id` (578) accepted by schema and defaulted server-side; `InvoiceItemIn.account_id` + `cost_center_id` accepted, consumed, and flow to GL. Pure UI gap.

**Frontend (`InvoiceFormView.vue`):**
- Header Debit-To/Credit-To `<select>` (after party ~570) bound to a filtered store getter. Add `receivableAccountOptions`/`payableAccountOptions` getters in `accounts.ts` filtering `account_type === 'Receivable'/'Payable'` (the `AccountNode` carries `account_type`). save() (245/251): `payload.debit_to_id = accountId.value || null` (sales) / `credit_to_id` (purchase).
- Make `gridColumns` a computed (like OrderFormView:102) and push `{key:'account_id',label: kind==='sales'?'Income Account':'Expense Account',type:'select',options:store.accountOptions}` and `{key:'cost_center_id',label:'Cost Center',type:'select',options:store.costCenterOptions}`. Seed `account_id:null, cost_center_id:null` in `newItemRow()` (136). No save() change — rows already carry them.
- Cost centers: add `costCenters` state + `fetchCostCenters()` + `costCenterOptions` getter to `accounts.ts` (mirror `fetchAccounts`). **Verify the endpoint name first** (likely `/cost-centers` or `/companies/{id}/cost-centers`) — this is an *unknown* to resolve before coding (C6).

**Verification:** `/sales-invoices/new` → pick a Debit-To = Receivable account; set a line Income Account + Cost Center; save; `GET /api/v1/sales-invoices/{id}` shows `debit_to_id`, per-line `income_account_id`, `cost_center_id`. Submit and confirm GL rows post to the chosen accounts.

### 3.2 — Group B: posting_time, update_stock (PI), is_paid/payments *(small migration + submit logic)*

These are genuinely riskier (new columns + submit-time GL/SLE). Recommend grouping the **column adds** into one migration and the **logic** behind the toggles.

- **posting_time:** no column anywhere. Add `posting_time` (Time, nullable) to `VoucherMixin`/`InvoiceMixin`; `posting_time: time|None` to `InvoiceCreateBase`. **Display-only** — GL/SLE chronology keys on `posting_date` only. The "Edit Posting Date and Time" toggle is pure frontend.
- **update_stock on PI:** column exists on SI (507) but **not PI** — add `update_stock` to `InvoiceMixin` so both share it (migration touches both tables). The actual stock movement (SLE on submit) is heavy and the file comments defer valuation to "Module 03" — **surfacing the toggle without SLE wiring is misleading.** Implement SLE posting in `submit_purchase_invoice` mirroring `purchase_receipt` before exposing it, or hold the toggle.
- **Payments tab (is_paid/paid_amount/mode_of_payment):** new columns + submit-time GL pair + outstanding/status recompute + **cancel must reverse the embedded payment** (the "payments allocated" guard at cancel must not block self-paid cancellation). Highest-effort in this tranche.

**Recommendation:** ship 3.1 in Tranche 3; schedule 3.2's `posting_time`/`update_stock`-column + payments into the same migration window as Tranche 6 (they share submit-logic risk).

**Migration:** `0026_invoice_accounting.py` — `posting_time` (both invoice tables via mixin), `update_stock` on PI, `is_paid/paid_amount/mode_of_payment_id/cash_bank_account_id`. New NOT-NULL cols need server_default; prefer nullable for `posting_time`, default false/0 for the rest. `PurchaseInvoiceItem.warehouse_id` (for accepted warehouse under update_stock) nullable.

---

# TRANCHE 4 — Payment Terms Template + Payment Schedule *(Priority #2)*

Highest-value remaining parity item but **high risk** because the document half needs new child tables across 5 docs + due-date resolution logic. Split into Track A (engine master, low risk) and Track B (documents, high risk). **Track A depends on Tranche 0.1** having registered `payment-terms-template` as a link source.

### 4.1 — Track A: Register the Payment Terms Template master *(machine-first, low risk)*

**Title:** Register the existing `PaymentTermsTemplate` (+ `PaymentTermsTemplateDetail` child) as an engine DocType.

**Migration:** **NONE for registration** — the master, child, table, FKs, and RLS already exist (`accounts.py:208-253`, migration `0002`). A small migration IS needed only if you expose ERPNext fields the table lacks (see C7).

**Backend (`descriptors.py`):** `register(DocTypeDescriptor(name='Payment Terms Template', slug='payment-terms-template', model=PaymentTermsTemplate, title_field='template_name', naming='field:template_name', group='Accounts', permission_name='Payment Terms Template', permissions={...Accounts Manager/User...}, fields=(FieldSpec('template_name',...,unique=True),), children=(ChildSpec(field='terms', model=PaymentTermsTemplateDetail, fk_column='template_id', fields=(...)),)))`. Add a `validate` hook replicating ERPNext: `sum(invoice_portion)==100`; reject duplicate term tuples. `seed_permissions` auto-grants from `descriptor.permissions`.

**Frontend:** `config/workspaces.ts` — add `{label:'Payment Terms Template', to:'/m/payment-terms-template'}` to the Accounting/Selling/Buying setup groups. Nav is manual, not auto-discovered. `GenericListView`/`GenericFormView`/`ChildGrid` render it.

**Schema-drift unknown (C7):** the live `PaymentTerm`/`PaymentTermsTemplate`/`Detail` models are **missing** ERPNext fields (`allocate_payment_based_on_payment_terms`, `credit_months`, `mode_of_payment`, `discount_*`, `description`). **Do NOT declare a `FieldSpec` for a column that doesn't exist — the engine will 500 on write.** Decide which to add now (separate small migration) vs. defer. Also: if the child's `payment_term_id` is a Link, you must register a `payment-term` descriptor/LINK_SOURCES entry or its `/options` 404s — simplest is to register Payment Term too, or drop the Link and keep free-form rows.

**Verification:** `/m/payment-terms-template/new` → snapshot the form + Payment Terms child grid. Add two terms (60% + 40%), save → succeeds. Add two terms summing to 90% → save → validate hook returns a 422 with the 100% message.

### 4.2 — Track B: Payment Schedule on the 5 documents *(high risk, bespoke)*

**Title:** Add `payment_terms_template_id` + a per-document `payment_schedule` child to Quotation/SO/SI/PO/PI, plus template-expansion + due-date logic.

**Migration:** REQUIRED + heavy. Add `payment_terms_template_id` to the 5 docs (FK to `payment_terms_templates`); create per-doc `*_payment_schedules` child tables (ERPNext `payment_schedule.json` fields: `payment_term_id, due_date, invoice_portion, payment_amount, description, mode_of_payment_id, paid_amount, outstanding, base_*`, idx). **Register every new child table in `RLS_TABLES`** or they bypass tenant isolation (follow `0002`'s canonical list). Note: child tables in `0005` are NOT in RLS — only parents are; **decide the convention** (C8: maps disagree on whether tax/schedule child tables get RLS — `0002` adds payment-terms tables to RLS, `0005` does not add buying child tables. Resolve before coding).

**Backend:** new `services/payment_terms.py` that, given `template_id + grand_total + posting_date`, expands details into schedule rows and computes `due_date` from `due_date_based_on/credit_days/credit_months` (ERPNext `accounts_controller.set_payment_schedule`). Resolve default template from `Customer/Supplier.payment_terms_template_id`, honoring `ignore_default_payment_terms_template` and doc-level override. Wire into each doc's create/submit; SI/PI `due_date` syncs to the last schedule row.

**Frontend:** add a Payment Terms section (template Link + `ChildGrid` schedule) to `InvoiceFormView`/`OrderFormView`.

**Verification:** create an SI with a 60/40 template → `GET /api/v1/sales-invoices/{id}` returns two `payment_schedule` rows with computed due dates summing to `grand_total`; `due_date` = the later schedule date.

---

# TRANCHE 5 — Per-line Margin + multi-UOM *(Priority #1, the high-risk half)*

**This is the single riskiest change in the program** because of stock-math correctness. Isolated into its own tranche, after the discount half (Tranche 1) is proven.

### 5.1 — Margin chain in the engine + columns

**Migration:** REQUIRED (additive). Add to `InvoiceItemMixin`: `margin_type` (String(20) nullable, 'Percentage'|'Amount'), `margin_rate_or_amount` (Numeric(21,6) default 0), `rate_with_margin` (Numeric(21,6) default 0). ALTER all 6 line tables (same blast radius as 1.1). Can fold into a `0027_line_margin_uom.py`.

**Backend:** `taxes_and_totals.py` `ItemRow` — add `margin_type, margin_rate_or_amount, rate_with_margin`. In `calculate_item_values` (178-187), insert margin **BEFORE** the discount block: `Percentage → rate_with_margin = price_list_rate*(1+margin/100)`; `Amount → price_list_rate+margin`; else `= price_list_rate`. Then treat `rate_with_margin` as the pre-discount base. This mirrors ERPNext's `price_list_rate → margin → rate_with_margin → discount → rate` chain. **Add unit tests** asserting the chain order and that Tranche 1's discount behavior is unchanged. Schemas: add `margin_type/margin_rate_or_amount` to `OrderItemIn`, echo `rate_with_margin`. Services persist the three. Frontend: margin columns + `applyMargin()` in `ItemsGrid.amountOf` and `utils/totals.ts`.

### 5.2 — Multi-UOM (PO) — **stock-math correctness is the trap**

**Migration:** add `conversion_factor` (Numeric(21,9) default 1), `stock_qty` (Numeric(21,6) default 0) to `InvoiceItemMixin`.

**Critical:** there is **NO UOM master / UOM Conversion Detail table** (stock.py:96-108 has only `stock_uom`). v1 must rely on a **client-supplied `conversion_factor`** (validated `gt=0`). The engine sets `stock_qty = qty*conversion_factor`; PO line rate = `price_list_rate(stock) * conversion_factor`. **Bin reserved/ordered updates (purchase_order.py:377, sales_order.py:361) and MR `ordered_qty` accrual (purchase_order.py:355) currently use `row.qty` — they MUST switch to `stock_qty` or inventory will be wrong.** `per_received/per_billed` and the fulfilment dialog must stay consistent in stock UOM. Keep `conversion_rate` (currency) and `conversion_factor` (UOM) strictly distinct.

**Verification:** create a PO with UOM=Box, conversion_factor=12, qty=5 → `GET /purchase-orders/{id}` shows `stock_qty=60`, `rate` = 12×stock-price; then check the Bin: `ordered_qty` increased by **60, not 5**. This Bin assertion is the make-or-break test.

---

# TRANCHE 6 — Delivery Note depth + Purchase Receipt depth *(Priorities #7 & #8)*

Largest surface; new tax tables, returns, and submit-logic. Sequenced so the **zero-migration sub-phases ship first**.

### 6.1 — DN Phase A: send `sales_order_item_id` from the standalone form *(zero migration, high value)*

**Title:** Make the standalone DN form carry the SO link so DNs accrue `delivered_qty`.

**Migration:** **NONE** — `DeliveryNoteItem.sales_order_item_id` (stock.py:554), schema, and full service support already exist; only the standalone form drops it.

**Frontend (`DeliveryNoteFormView.vue`):** add `GetItemsFrom` (sources=`[{label:'Sales Order',param:'sales_order_id',endpoint:'/sales-orders'}]`); add `prefill()` reading `route.query.sales_order_id`, GET the SO, map pending rows (`qty-delivered_qty>0`) to lines carrying `sales_order_item_id: row.id` (copy OrderFormView prefill 325-340 / createFulfilment 214-237). Extend `DnItemIn` + save() to include `sales_order_item_id`.

**Verification:** `/delivery-notes/new?sales_order_id=<id>` → grid prefills pending lines; save; `GET /sales-orders/{id}` shows `delivered_qty` accrued on the linked line.

### 6.2 — PR: Get-Items-From-PO on the standalone form *(zero migration)*

**Migration:** NONE — `PurchaseReceiptItem.purchase_order_item_id` + PO_RECEIPT cap already exist.

**Frontend (`PurchaseReceiptFormView.vue`):** import `GetItemsFrom`; `prefill()` from `?purchase_order_id=` filtering pending rows (`qty-received_qty>0`), mapping to rows with `purchase_order_item_id` — same payload shape as `createFulfilment` (OrderFormView 214-237). **Keep ONE payload contract** so PO→PR is identical from both entry points.

### 6.3 — DN Phase B: Taxes/Discount/Totals + TotalsMixin refactor *(migration)*

**Title:** Give DN a tax child table + full totals.

**Migration:** Switch `DeliveryNote` to inherit `TotalsMixin` — **remove its duplicate inline columns** (`currency, conversion_rate, total_qty, base_total, grand_total, base_grand_total` — verified present at stock.py:503-523) to avoid SQLAlchemy conflicts, and **ADD only the missing TotalsMixin columns** (`total, net_total, base_net_total, total_taxes_and_charges, base_total_taxes_and_charges, apply_discount_on, additional_discount_percentage, discount_amount, rounded_total, rounding_adjustment`). Create `delivery_note_taxes` (mirror `SalesOrderTax` selling.py:620-627). Watch column-name overlap precisely — this is the trickiest migration in the program.

**Backend:** add `DeliveryNoteTax`; `create_delivery_note` runs `_load_tax_rows` + `calculate_taxes_and_totals` (copy sales_order.py:71-97,163-272), persists header totals + tax rows.

**CORRECTNESS TRAP (verified design decision):** ERPNext and this codebase (stock.py:14-15) **deliberately post ONLY COGS on DN submit**; revenue+tax post on the invoice. **DN taxes/discount are display + downstream-prefill only — do NOT add tax/discount GL on DN submit** or you double-count when the invoice posts.

### 6.4 — DN Phase C/D + PR depth: PO/return columns, accepted/rejected split

- **DN Customer PO (Phase C):** add `po_no/po_date` to DN (mirror SO selling.py:568-569).
- **DN Returns (Phase D):** add `is_return + return_against_id`; require `return_against_id` when `is_return`; thread `sign=-1` (machinery in `cycle_links` already supports signed deltas); submit makes positive SLE-IN + reverses COGS.
- **PR accepted/rejected split:** add `rejected_qty` + `rejected_warehouse_id` to `PurchaseReceiptItem`; keep `qty` = accepted (ERPNext: `received_qty = accepted + rejected`). **PO_RECEIPT delta must use `qty+rejected_qty`** or rejected receipts never close the PO. Submit emits SLE-in for accepted→warehouse and a second SLE-in for rejected→rejected_warehouse; cancel reverses both.
- **PR Returns + Supplier Delivery Note:** add `is_return/return_against_id/supplier_delivery_note` (mirror PI accounts.py:579-583). **Memory note:** PI Debit Note deliberately seeds `bill_no+bill_date` — keep that seeding convention if mirroring onto PR returns; don't leave blank.
- **PR country/default_price_list on masters:** add `country` (String(140), free-text Data like Address.country) + `default_price_list_id` (FK price_lists) to Customer+Supplier (model + descriptor + migration). To make default price list a Link, register `price-list` in LINK_SOURCES.

**PR Taxes — DESIGN REVERSAL, confirm before building (C9):** `stock.py` top docstring + the PR form header both state "PRs carry no taxes; taxes apply on the invoice." Adding PR taxes changes valuation/landed-cost semantics on submit. **Confirm scope with the team before building PR taxes** — it is the heaviest gap and contradicts the stated design.

### 6.5 — Amend (DN, PR, SQ) — **no in-repo precedent**

`amended_from_id` exists on `VoucherMixin` everywhere, but **no service implements amend** (grep confirms zero amend logic). This must be designed from scratch (ERPNext: amend = clone a cancelled doc into a new Draft with `amended_from_id` set, name suffix `-1`; decide whether per-row links carry over). **Lowest priority / highest uncertainty — defer to a dedicated design task.**

---

## Contradictions, unknowns, and design reversals to resolve BEFORE coding

| # | Issue | Where | Resolution needed |
|---|---|---|---|
| **C1** | Some maps say a new buying migration is "0007_*"; the buying-terms map says "00XX". **Actual head is `0023_buying_address_contact`; next free number is `0024`.** Multiple tranches all want "0024" — they must be numbered sequentially (0024, 0025, …) not all 0024. | All migration maps | Assign sequential numbers as you land tranches; never two `0024`s. |
| **C2** | Two silent-drop paths for Customer/Supplier: the engine (`/registry`) and bespoke `/accounts` (`schemas/accounts.py:14-53`). | Master map | Confirm which the UI calls; default = engine only. |
| **C3** | Tax picker: inline `taxes` vs `tax_template_id` precedence — sending both makes the template "look ignored." | Tax map | Pick model (a) populate-rows-and-don't-send-template. |
| **C4** | More-Info: Project/Opportunity/Sales Team have **no masters** — `resolve_link_source` returns None. | More-Info map | Wire only the 5 that have masters; defer the rest as an epic. |
| **C5** | RFQ has **no single party** (multi-supplier) — `AddressContactTab`'s one-party contract doesn't fit. Prompt lists RFQ as an A&C target but the model fights it. | A&C map | Defer RFQ A&C or scope to shipping-only `<select>`. |
| **C6** | Cost-center fetch endpoint name unknown (`/cost-centers` vs `/companies/{id}/cost-centers`). | Invoice map | Verify endpoint before adding the store action. |
| **C7** | Payment Terms models are **missing** ERPNext fields; declaring a FieldSpec for a non-existent column 500s the engine. Also `payment_term_id` Link needs a resolvable target. | Payment Terms map | Decide which fields to add (small migration) vs defer; register Payment Term or drop the Link. |
| **C8** | RLS inconsistency: `0002` adds payment-terms child tables to `RLS_TABLES`; `0005` does NOT add buying tax/item child tables. New child tables (DN tax, payment schedules, SQ tax) — RLS or not? | Multiple | Pick one convention; new tenant child tables should likely be in RLS_TABLES — confirm. |
| **C9** | **Design reversals:** PR taxes (stock.py:14-15 says "no taxes on PR") and adding taxes to DN both contradict explicit "taxes post on the invoice" design notes. Surfacing `update_stock` on PI without SLE wiring is a no-op toggle. | DN/PR/Invoice maps | Confirm scope with team; if adding DN taxes, keep them display-only (no GL on submit). |
| **C10** | Multi-UOM has **no UOM master/conversion table**; v1 is client-supplied `conversion_factor`. The real risk is Bin/MR stock math still on `row.qty`. | Trade-form map | Switch all stock accrual to `stock_qty`; verify with a Bin assertion. |

## One-line summary of ordering rationale

Do the **zero-migration declarative/UI wins first** (Tranche 0–1 discount, 3.1, 6.1–6.2), because they deliver visible parity with near-zero risk and several unblock later items; defer the **new-table / submit-logic / stock-correctness** work (Payment Schedule docs, Margin+UOM, DN/PR taxes & returns, Amend) to later tranches where the risk is concentrated and individually testable. The two biggest correctness traps — **multi-UOM stock math** (Bin must use `stock_qty`) and **DN/PR taxes must not post GL on submit** — are called out inline so they aren't discovered in production.