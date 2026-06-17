# Selling & Buying — OptiReach ERP vs ERPNext Parity Report

_Generated 2026-06-17. Method: Playwright captured both apps (OptiReach @ localhost, ERPNext staging
via saved session) — full-page screenshots + accessibility field-dumps in `e2e/out/` and
`e2e/out/erpnext/`. Because a live Frappe form only renders its **active tab**, the authoritative
field list for ERPNext is its **source DocType JSON** (`reference/erpnext/…`), not the screenshot.
Each document was audited (ERPNext source + capture vs our backend schema + frontend form) and then
**adversarially verified** — every "missing" claim re-checked against our code, which corrected
several false positives (e.g. Sales Order, Purchase Order, Material Request were undercounted)._

> **Reading the scores.** The percentage is approximate **everyday-core coverage** (the fields/
> features a typical user touches), not a raw field count. ERPNext documents carry dozens of
> advanced accounting/manufacturing/dimension fields most businesses never use; those are excluded
> from "core." Treat the bands, not the exact numbers, as the signal.

---

## Scorecard

| Module | Document | Core coverage | Status |
|---|---|---|---|
| Selling | **Sales Order** | ~92% | 🟢 Strong |
| Selling | **Quotation** | ~88% | 🟢 Strong |
| Buying | **Purchase Order** | ~88% | 🟢 Strong |
| Buying | **Material Request** | ~88% | 🟢 Strong |
| Selling | **Sales Invoice** | ~68% | 🟡 Moderate |
| Buying | **Purchase Invoice** | ~59% | 🟡 Moderate |
| Buying | **Supplier** (master) | ~54% | 🟡 Moderate |
| Buying | **Request for Quotation** | ~54% | 🟡 Moderate |
| Selling | **Delivery Note** | ~52% | 🟡 Moderate |
| Buying | **Supplier Quotation** | ~44% | 🟠 Thin |
| Selling | **Customer** (master) | ~38% | 🟠 Thin |
| Buying | **Purchase Receipt** | ~28% | 🔴 Minimal (by design) |

**The headline:** the core *order* flow on both sides (Quotation → Sales Order, Material Request →
Purchase Order) is in strong shape. The gaps cluster in (a) **billing depth** (invoices), (b)
**masters** (Customer/Supplier are thin), (c) **fulfilment documents** (Delivery Note, Purchase
Receipt), and (d) a handful of **cross-cutting fields** missing almost everywhere.

---

## Cross-cutting gaps (the highest-leverage fixes)

These each appear on *many* documents, so one feature closes several gaps at once:

1. **Per-line Discount / Margin** — missing on Quotation, Sales Order, Purchase Order, Sales Invoice,
   Purchase Invoice. Today only a single **document-level** "Additional Discount" exists; ERPNext lets
   you discount each line. This is the single most-requested everyday field absent today.
2. **Payment Terms Template + Payment Schedule** — Quotation, SO, Sales Invoice, PO, Purchase Invoice,
   Customer, Supplier all lack installment/due-date scheduling. Our "Terms" is free-text only.
3. **The shared "More Info" tab is an empty placeholder** on the trade form (Quotation / SO / PO) —
   it literally renders _"This section isn't built yet."_ (Campaign, Source, Territory, Project,
   Sales Team live here in ERPNext.)
4. **Address & Contact tab unbuilt** on Delivery Note, RFQ, and Supplier Quotation (it exists and
   works on Orders/Invoices — just not wired into these three).
5. **Tax Category / tax-template picker** — we support manual tax rows but not ERPNext's
   template-driven taxes + tax category.
6. **Masters drop fields the DB already has.** Customer and Supplier are served by the metadata
   engine, whose request models use `extra="ignore"` — so columns that *exist* on the model
   (`payment_terms_template_id`, `tax_category_id`) are silently dropped because the descriptor
   doesn't list them. Adding them to the descriptor surfaces them with zero migration.

---

## Where OptiReach is *better* / deliberately different

The clone isn't strictly behind — several flows are tighter than stock ERPNext:

- **One shared trade form** drives Quotation, Sales Order and Purchase Order → consistent UX.
- **Sourcing cockpit:** RFQ and Supplier Quotation live on one screen with per-supplier quote-status
  badges; "record quote" prefills an SQ from an RFQ and flips status to Received; "make PO" prefills a
  PO from quoted rates — a tighter loop than ERPNext's disconnected forms.
- **Inline fulfilment dialogs** — "Receive pending items" on a PO drafts a Purchase Receipt with
  per-row pending qty; the SO sibling drafts a Delivery Note — more guided than ERPNext's generic
  Create ▸ menu.
- **CSV / Tally Import** on every items grid (bulk-append by item code).
- **Inline quick-add party** (create a Customer/Supplier without leaving the document).
- **Auto rate resolution** (price list → blanket order → pricing rule → coupon) applied server-side.
- **Debit Note auto-seeds** Supplier Invoice No./Date from the return-against invoice.
- **Friendly client-side validation** (plain-language messages instead of raw 422s).

---

## Per-document detail

### 🟢 Sales Order — ~92%
Strongest document. Confirmed core gaps: **Scan Barcode** (no scan-to-add box) and **per-line
Discount % / Margin**. Advanced/missing: Project, header Cost Center, Tax Category, Incoterm, Sales
Team, Auto Repeat, Reserve Stock, Drop Ship, Item Tax Template. _Extras:_ credit-limit warnings
banner on submit; Get-Items-From Quotation.

### 🟢 Quotation — ~88%
Confirmed core gaps: **"More Info" tab is a placeholder** (Campaign, Source, Territory, Customer
Group, Opportunity); **Set-as-Lost workflow** (Lost status + lost reasons/competitors; status enum
is only Draft/Open/Ordered/Cancelled — missing Replied/Partially Ordered/Expired). Coupon Code &
Shipping Rule are accepted by the backend but not surfaced.

### 🟢 Purchase Order — ~88%
Confirmed core gaps: **per-line Discount/margin** and **multi-UOM** (UOM conversion factor → stock
qty; only a single free-text UOM today). Header Tax Category / Cost Center / Project are resolved
internally but not user-overridable. _Extras:_ "Receive pending items" dialog; clearer "Expected
Receipt" labelling.

### 🟢 Material Request — ~88%
Confirmed core gap: **header Set Target Warehouse** (`set_warehouse`) that cascades to lines (only
per-line warehouse exists). Cancel/Amend exist server-side but aren't surfaced. Material-Transfer
source warehouse + Manufacture/Customer-Provided purposes deferred. _Extras:_ one-click "order" → PO;
inline row submit.

### 🟡 Sales Invoice — ~68%
Confirmed core gaps: **Posting Time + "Edit Posting Date and Time"** (backdating); **Payment Terms +
Schedule**; **per-line discount/margin**. _Verified nuance:_ Debit-To (receivable) account, per-line
Income Account and Cost Center **are accepted by the backend but hidden in the UI** → surface them.
_Extras:_ quick-add Customer; "Receive Payment" deep-link to a prefilled Payment Entry.

### 🟡 Purchase Invoice — ~59%
Confirmed core gaps: **Credit-To (payable) selector** (backend defaults it silently); **Payments tab**
is a "coming soon" placeholder (Is Paid / Mode of Payment / Paid Amount); **Update Stock + Accepted
Warehouse**; **Cost Center** (schema has `cost_center_id` on items but the grid never shows it).
_Extras:_ quick-add Supplier; Debit-Note bill-no/date auto-seed; live client-side totals.

### 🟡 Supplier (master) — ~54%
Confirmed core gaps: **country**, **default price list**, **default payment terms** (column exists,
dropped by `extra="ignore"`), **primary address/contact + mobile/email** (only a save-first
placeholder). Billing Currency is free-text instead of a Currency link. _Extras:_ company-scoped
multi-tenant isolation.

### 🟡 Request for Quotation — ~54%
Confirmed core gaps: **Company** & **Subject** fields; **Terms & Conditions** (Terms Template master
exists in the sidebar but is unwired); **Address & Contact tab**; **Get Items From Material Request**
(+ `material_request_item_id` linkage); per-item **description**. _Note:_ UOM/Warehouse/Required-Date
are backend-accepted — just surface the columns. _Extras:_ the sourcing cockpit (above).

### 🟡 Delivery Note — ~52%
Confirmed core gaps: **Taxes & Charges**, **Additional Discount**, **returns/credit-note flow**, **Get
Items From Sales Order** (the authoring screen never sends `sales_order_item_id`), **Submit/Cancel/
Amend on the form**, **Address & Contact tab**, **Customer PO details**, per-line pricing columns. The
standalone DN form is a hand-keyed draft today. _Extras:_ remarks field; warehouse-fallback hint.

### 🟠 Supplier Quotation — ~44%
Lean "record a quote" surface (doesn't inherit the shared order base, so no taxes/warehouse/terms).
Confirmed core gaps: **no dedicated detail/edit view** (a saved quote can only spawn a PO — never be
reopened or corrected), **Terms tab**, **Purchase Taxes table**, **per-item Warehouse**, supplier's
**Quotation Number**, **Amend**. _Extras:_ "make PO" + "record quote" sourcing flow.

### 🟠 Customer (master) — ~38%
Thinnest master. 9-field descriptor only. Confirmed core gaps: **default price list**, **default
payment terms** (column exists, dropped by engine), **primary contact + mobile/email**, **primary
address**, **tax category** (column exists, dropped). `customer_type` only Company/Individual (missing
Partnership); currency is free-text. _Extras:_ engine-driven list + inline Address/Contact after save.

### 🔴 Purchase Receipt — ~28% (minimal by design)
Intentionally an "ad-hoc goods receipt" (supplier, date, currency, target warehouse, item lines).
Missing the defining PR features: **accepted/rejected quantity split + Rejected Warehouse**, **Taxes &
totals/rounding**, **Submit/Cancel lifecycle**, **Is Return / Return Against**, **Get Items From
(PO/MR/PI)**, **Supplier Delivery Note**, serial/batch capture. _Note:_ PR-from-PO already works via
the PO "Receive pending items" dialog; this standalone form is the deferred piece (see BE backlog).
_Extras:_ Import, auto-rate, friendly validation.

---

## Recommended priorities (ranked by leverage)

1. **Per-line Discount / Margin** on the shared items grid — closes a core gap on 5 documents at once.
2. **Payment Terms Template + Payment Schedule** — touches 7 documents; replaces free-text Terms.
3. **Build the shared "More Info" tab** (Quotation/SO/PO) — removes the visible "not built yet" stub.
4. **Wire the Address & Contact tab** into Delivery Note, RFQ, Supplier Quotation (component already exists).
5. **Flesh out Customer & Supplier masters** — add default price list + primary contact/address +
   mobile/email; expose the orphaned `payment_terms_template_id` / `tax_category_id` columns in the
   descriptor (no migration needed).
6. **Surface backend-hidden accounting fields** on invoices — Debit-To / Credit-To, per-line Income
   Account + Cost Center (all already accepted by the backend).
7. **Delivery Note depth** — Taxes/Discount/totals + Get-Items-From-SO + Submit/Cancel on the form.
8. **Purchase Receipt** — accepted/rejected split + taxes + lifecycle, *if* formal goods-receipt
   matters to the business (otherwise the PO dialog covers the common path).
