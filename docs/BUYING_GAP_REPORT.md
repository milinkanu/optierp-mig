# Buying Module — ERPNext vs OptiERP Gap Report & Implementation Plan

> **Method (hybrid):** every screen diffed across three sources — ERPNext **source**
> (`reference/erpnext`, v15 doctype JSON), the **live** ERPNext desk
> (`/buying`, captured to `e2e/out/erpnext/`), and **our** implementation. ERPNext
> version matches the staging instance (v15).
>
> **Scope:** the Buying supply chain (Material Request → RFQ → Supplier Quotation →
> Purchase Order → Purchase Receipt → Purchase Invoice) + Buying masters/settings.

---

## 1. Executive summary

Buying is **further along than Selling was** when we started — the whole transaction
chain exists, and Purchase Order / Purchase Invoice already inherit the shared
commercial blocks we built for Selling (Currency, Taxes, Additional Discount, Totals,
Import, Terms). The gaps cluster into four themes:

1. **No Buying masters** — Supplier and Supplier Group are *not* engine-managed (the
   mirror image of Selling's Customer/Customer Group). Supplier is a bespoke model with
   only a name-only quick-add; Supplier Group doesn't exist.
2. **Supplier Address & Contact** — the A&C tab is **selling-only**; Purchase docs can't
   pick a supplier address/contact.
3. **Purchase Receipt is view-only** — no create/edit form, no accepted/rejected split,
   no taxes (Delivery Note *has* a form; PR doesn't).
4. **Thin create forms** — Material Request (no type selector, no per-item warehouse/required-by in the form), RFQ (no email/send workflow, schedule/message not rendered), Supplier Quotation (valid_till/currency not rendered) — much of this is **already in the backend, just not surfaced in the form**.

| Document | Our coverage | Headline gaps |
|---|---|---|
| **Purchase Order** | ~70% | supplier A&C, Set Target Warehouse (modeled, not sent), payment terms, subcontracting/drop-ship, tax template/category |
| **Purchase Invoice** | ~55% | **bill_no/bill_date inputs missing on the create form** (backend has them!), Is-Return label says "Credit Note" not "Debit Note", supplier A&C, Update Stock, TDS, Hold, Payment Terms, Advances |
| **Material Request** | ~40% | type selector (hard-codes "Purchase"; no Manufacture/Customer-Provided), per-item warehouse + required-by not in form, set_warehouse |
| **Purchase Receipt** | ~10% (view-only) | **no create form**, accepted/rejected qty split, rejected warehouse, taxes/totals, is_return |
| **RFQ** | ~45% | email/portal send workflow, schedule_date + message_for_supplier not rendered, Get-Items-From Material Request |
| **Supplier Quotation** | ~40% | valid_till + currency not rendered, no taxes rows, folded into /sourcing (no standalone screen) |

Nothing is broken — these are unbuilt breadth and a few unsurfaced fields.

---

## 2. What's already built (Buying is not starting from scratch)
- The full chain MR → RFQ → SQ → PO → PR → PI exists with submit/cancel + status rollups (`per_received`/`per_billed`/`per_ordered`).
- **Purchase Order** (shared `OrderFormView`, `kind="purchase-order"`): supplier, items grid with **Item/Service · Required-By · Qty · UOM · Rate · Warehouse**, **Currency · Taxes & Charges · Additional Discount · Totals (incl. client-side in-words preview) · Import (CSV/Tally) · Terms tab**, Get Items From (Material Request / Supplier Quotation), tracking.
- **Purchase Invoice** (shared `InvoiceFormView`, `kind="purchase"`): same commercial blocks + Terms, plus **Is-Return** + return_against, and `bill_no`/`bill_date` **in the backend + detail view**. Get Items From (Purchase Order / Purchase Receipt).
- **Buying terms** persist on PO and PI (added this session).

---

## 3. Cross-cutting gaps → fix once, reuse across Buying

These mirror the Selling Phase A–D work and reuse the components we already built:

| Theme | Reuse | What's missing for Buying |
|---|---|---|
| **Supplier Address & Contact** | `AddressContactTab` (already supports `party-kind="supplier"`); `LinkSpec` party FKs already exist on Address/Contact | add `supplier_address_id`/`shipping_address_id`/`contact_person_id` to PO/PI (and PR/SQ) models+schemas+services+migration; render the A&C tab for purchase kinds |
| **Set Target Warehouse (header)** | header field pattern | PO/PR models already have `set_warehouse_id`; the **form never renders/sends it** |
| **Tax template / category / shipping / incoterm** | the `TaxesCharges` editor exists | the template *picker* + `tax_category`/`shipping_rule`/`incoterm` selectors — deferred subsystem (shared with Selling) |
| **Payment terms + schedule** | — | `payment_terms_template` + `payment_schedule` child table — a subsystem shared Selling+Buying (models partly exist, unwired) |

---

## 4. Per-document gap detail (condensed)

### 4.1 Purchase Order — ~70%
**Have:** supplier, Required-By (header + per-row), items grid (incl. UOM + Warehouse), Currency, Taxes, Additional Discount, Totals, Import, Terms, Get-Items-From (MR/SQ), per_received/per_billed.
**Gaps:** **supplier Address & Contact tab** (selling-only); **Set Target Warehouse** header (modeled `set_warehouse_id`, not sent); **payment terms/schedule** + `tc_name` template link; tax template picker / `tax_category` / `shipping_rule` / `incoterm`; price list selection; per-line discount/margin; **subcontracting** (`is_subcontracted`, supplier warehouse, raw-materials-supplied) and **Drop Ship** tabs; TDS; print/auto-repeat/inter-company. Order Type rendered but not persisted.

### 4.2 Purchase Invoice — ~55%
**Have:** supplier, posting/due dates, items grid, Currency/Taxes/Discount/Totals, Terms, Is-Return + return_against; `bill_no`/`bill_date` + `credit_to` in backend.
**Real, cheap fixes:** ⚠️ **the create form has no inputs for Supplier Invoice No (`bill_no`) / Date (`bill_date`)** even though the backend accepts them; ⚠️ the Is-Return checkbox label is hard-coded **"Credit Note"** — for purchase it should read **"Debit Note"**.
**Bigger gaps:** supplier A&C; **Update Stock** + per-item warehouse (InvoiceItemIn has no `warehouse_id`); **Hold Invoice** (on_hold/release_date); **Tax Withholding / TDS**; **Payment Terms/Schedule**; **Advances/Allocation** (`advance_paid` modeled, no UI); Write-Off; `credit_to` GL picker (required in ERPNext, defaulted+hidden in ours).

### 4.3 Material Request — ~40%
**Have:** list + a lightweight inline create (date, required-by, item+qty) → Save/Submit; row "order" → prefilled PO; per_ordered rollup; backend stores type, per-item warehouse + schedule_date.
**Gaps:** **type selector missing** (form hard-codes "Purchase"; API `pattern` blocks **Manufacture**/**Customer Provided**, and the dependent `customer` field); **per-item warehouse + required-by not in the create form** (already in the model/schema — cheapest high-value win); header `set_warehouse`/`set_from_warehouse`; `per_received` + Received/Transferred/Issued statuses; Get-Items-From.

### 4.4 Purchase Receipt — ~10% (biggest structural gap)
**Have:** **view-only** `FulfilmentView` (shared with Delivery Note) — list + read-only detail + Submit/Cancel/Create-Invoice. Backend `create_purchase_receipt` exists (PR-from-PO via `purchase_order_item_id`).
**Gaps:** **no create/edit screen and no "New PR"/"Get Items From PO" entry point**; **accepted vs rejected qty split** (`received_qty`/`rejected_qty`) + `rejected_warehouse`; **taxes/totals** (PR has no tax rows, no net_total/rounding/in-words, no additional discount); **is_return** + `MAT-PR-RET` series + per_returned; supplier address/contact; transporter info; `posting_time`.

### 4.5 Request for Quotation — ~45%
**Have:** two-tab "Sourcing" page (`/sourcing`); RFQ keeps the **items grid + suppliers grid** with per-supplier `quote_status` (Pending/Received).
**Gaps:** the entire **email/portal send workflow** (email_template, subject, message delivery, per-supplier send_email/email_sent, preview); **schedule_date** + **message_for_supplier** modeled but **not rendered**; Get-Items-From **Material Request** (no MR link on RFQ items); terms; billing address; opportunity.

### 4.6 Supplier Quotation — ~40%
**Have:** folded into the Sourcing page (no standalone screen); supplier, items (item/qty/rate), RFQ→SQ link (`rfq_item_id`), status incl. **Ordered**, SQ→PO conversion (`supplier_quotation_id`).
**Gaps:** **valid_till** + **currency** modeled but **not rendered**; **no tax rows** (deliberately deferred to PO) → no taxes/discount/rounding/in-words; Get-Items-From Material Request; per-line discount/lead-time/expected-delivery; standalone screen; Stopped/Expired statuses.

---

## 5. Masters coverage

| ERPNext master | In ours? | Path to parity | Notes |
|---|---|---|---|
| **Supplier** | Bespoke model only (name-only quick-add); `/m/supplier` doesn't exist; workspace link `planned` | **Recipe card** (highest value) | Model already has supplier_type, tax_id, default_currency, payable_account_id, payment_terms_template_id, tax_category_id, disabled, notes. Add `supplier_group_id` + `on_hold`/`hold_type`/`release_date`; register a descriptor cloned from Customer; wire Address/Contact via `links` (party-kind "supplier" — FKs already exist) |
| **Supplier Group** | ❌ (deferred; suppliers carry free-text type) | **Recipe card** (tree) | Direct clone of Customer Group tree: 1 migration + thin tree model + descriptor + perms; then add `Supplier.supplier_group_id` |
| **Buying Settings** | ⚠️ workspace → generic `/settings` | **Defer** | No singleton-DocType mechanism yet; only `po_required`/`pr_required` gating is likely wanted soon |
| **Purchase Taxes & Charges Template** | ❌ (`planned`) | **Defer** | Bundle with Selling Tax Template + Tax Category (child-table master, doesn't fit the flat recipe-card cheaply) |
| **Supplier Scorecard** (8 doctypes) | ❌ | **Out of scope** | Full periodic-scoring analytics subsystem; the Supplier `on_hold` block is the cheap manual substitute |

---

## 6. Implementation plan (phased, prioritized)

**Phase BA — Buying masters as recipe cards (highest value, lowest cost; pure engine config)**
1. **Supplier Group** — tree recipe card cloned from Customer Group (migration + thin tree model + descriptor + perms).
2. **Supplier** — register a descriptor (reuse the existing model); add `supplier_group_id` + `on_hold`/`hold_type`/`release_date`; wire **Address/Contact inline** via `links`/`LinkSpec` (party-kind "supplier"). Flip the `planned: true` Supplier/Supplier-Group links in `workspaces.ts` to `/m/supplier` and `/m/supplier-group`. Keep the name-only quick-add for inline creation on PO forms.

**Phase BB — Supplier Address & Contact on transactions (mirror Selling A&C)**
3. Add `supplier_address_id`/`shipping_address_id`/`contact_person_id` to Purchase Order + Purchase Invoice (models, schemas, services, one migration), and render `AddressContactTab` with `party-kind="supplier"` for the purchase kinds (the component already supports it).

**Phase BC — Surface fields the backend already supports (cheap wins)**
4. **Purchase Invoice create form:** add **Supplier Invoice No (`bill_no`) + Date (`bill_date`)** inputs; relabel Is-Return to **"Debit Note"** for purchase.
5. **Purchase Order:** add the **Set Target Warehouse** header field (`set_warehouse_id`).
6. **Material Request:** add the **type selector** (Purchase / Material Transfer / Material Issue / Manufacture / Customer Provided; widen the API pattern + dependent `customer`), and the **per-item Warehouse + Required-By** columns in the create form.
7. **RFQ:** render **schedule_date** + **message_for_supplier**. **Supplier Quotation:** render **valid_till** + **currency**.

**Phase BD — Purchase Receipt create form (structural)**
8. Build a standalone **Purchase Receipt** create/edit form (mirror the Delivery Note form): Get-Items-From **Purchase Order**, **accepted/rejected qty split** + rejected warehouse, set warehouse, and the shared commercial blocks. Add a "New Purchase Receipt" entry point.

**Phase BE — Deferred subsystems (don't build now; note as roadmap)**
- Payment Terms + Schedule (shared Selling+Buying child-table subsystem).
- Tax Template / Tax Category / Shipping Rule / Incoterm masters.
- Update Stock + perpetual inventory on PI/PR; Tax Withholding (TDS); Hold Invoice; Advances/Allocation; Write-Off.
- Subcontracting (Drop Ship, Raw-Materials-Supplied) — large.
- RFQ email/portal send workflow.

---

## 7. Out of scope (explicit)
- **Supplier Scorecard** (8 doctypes + periodic scoring job) — use Supplier `on_hold` as the manual substitute.
- **Subcontracting** end-to-end (BOM explosion, FG items, raw-material transfer).
- **Buying Settings** as a real singleton DocType (keep the generic `/settings` pointer).
- Scan Barcode, print/letterhead settings, auto-repeat/subscription, inter-company.

---

## 8. References
- Source: `reference/erpnext/erpnext/{buying,stock,accounts,setup}/doctype/*` (v15)
- Live captures: `e2e/out/erpnext/app-{purchase-order,purchase-invoice,supplier,material-request,buying}-new.png`
- Ours: `frontend/src/views/trade/OrderFormView.vue` (PO), `frontend/src/views/accounts/InvoiceFormView.vue` (PI), `frontend/src/views/stock/MaterialRequestView.vue`, `frontend/src/views/trade/FulfilmentView.vue` (PR), `frontend/src/views/buying/RfqView.vue` (RFQ/SQ); `backend/app/{models,schemas,services}/buying.py`; `backend/app/registry/descriptors.py`
