# 05 · Taxes

> Sub‑module of [ACCOUNTING_GAP_AND_PLAN.md](../ACCOUNTING_GAP_AND_PLAN.md). ERPNext workspace card: **Taxes**.

## Status today — 🟡 templates & engine done, automation & compliance missing

- **Tax Template (Sales/Purchase)** ([accounts_masters.py](../../backend/app/services/accounts_masters.py)):
  header + rows; 5 charge types (Actual, On Net Total, On Previous Row Amount/Total, On Item Quantity);
  Add/Deduct; Valuation/Total categories; per‑company default; resolves by party's Tax Category.
- **Tax Category** — ✅ master.
- **Taxes & Totals engine** ([taxes_and_totals.py](../../backend/app/services/taxes_and_totals.py)):
  faithful ERPNext port — per‑item chaining, multi‑currency, additional discount, rounding.
- **No dedicated Tax Template UI** (managed inline on invoices; card `planned`).

## Gaps vs ERPNext

| # | Gap | State | P | Why |
|---|---|---|---|---|
| 1 | **Inclusive taxes** (`included_in_print_rate`) | 🔴 blocked | 1 | Engine raises `ValidationError`. MRP/retail pricing is tax‑inclusive. Back‑compute net rate. |
| 2 | **Tax Template editor UI** | 🔴 (backend done) | 1 | Dedicated list/form to replace the `planned` card. Pure frontend + the existing create/list API. |
| 3 | **Tax Withholding (TDS/TCS)** | 🔴 | 2 | India legal requirement — deduct tax at source on supplier payments/invoices above thresholds, accumulate, report. |
| 4 | **Item Tax Template** (per‑item rate override) | 🔴 | 3 | Mixed‑GST‑slab catalogs (5% / 12% / 18% items on one invoice). |
| 5 | **Tax Rule** (auto‑select template) | 🔴 | 3 | Pick the right template by party/territory/category automatically. |
| 6 | **TDS reports** (withholding details, computation summary) | 🔴 | 3 | Pair with #3. |
| 7 | **Advance tax** (tax on advance receipts) | 🟡 | 3 | GST on advances — couples to [02-payments.md](02-payments.md) advances. |

## Simplifications

- **No regional VAT line mapping** (`south_africa_vat_account` et al.) — generic templates only (master §3.5).
- **Tax Rule lean**: match on party + tax category + territory only; skip the full applicability‑filter
  child‑table matrix. One rule → one template.
- **TDS at our scale**: category + rate + threshold + payable account. Deduct on payment (or invoice,
  configurable). Skip the cumulative multi‑voucher edge cases until volume demands.

## Build‑out

### Phase 1 — Unblock & surface
- ✅ **Inclusive taxes** DONE (2026‑06‑19, *bespoke — posting math*): `taxes_and_totals` now ports
  ERPNext's `determine_exclusive_rate` — when `included_in_print_rate` is set the line rate is
  treated as tax‑inclusive and the net rate is back‑calculated via the cumulative tax fraction,
  with a rounding‑reconciliation step (`manipulate_grand_total_for_inclusive_tax`) so the grand
  total matches the sum of inclusive line amounts. `included_in_print_rate` added to the shared
  `TaxRowMixin` (migration 0038 — `tax_template_details` + the five transaction tax child tables),
  plumbed through Sales/Purchase Invoice (calc + persisted row), and surfaced as a template‑level
  **"tax‑inclusive (MRP)"** toggle + an `INCL` badge in the Tax Template editor. 'Actual' charge
  rows can't be inclusive (validation). 5 new unit tests; live‑verified.
- ✅ **Tax Template editor** DONE (Phase 0/0.5): list + create + edit + delete, sales/purchase toggle.
- *Acceptance met:* an inclusive 18% line on a ₹118 MRP yields net ₹100 / tax ₹18 / grand ₹118
  (= the exclusive equivalent's grand total); tax templates are full CRUD in the UI.

### Phase 2 — Automation & compliance
- **Item Tax Template** (*engine master + invoice hook*): per‑item account→rate override; the invoice
  taxes step honors it. Engine for the master; small hook in the tax resolution.
- **Tax Rule** (*engine master + resolution hook*): declarative rule; resolution picks the template at
  invoice creation. Engine master + a resolver function (extends current "party category → template").
- **Tax Withholding / TDS** (*bespoke — posting*):
  - `Tax Withholding Category` master (rate, threshold, payable account) — **engine**.
  - On supplier payment/invoice, compute and post the TDS deduction row (Dr expense net, Cr payable, Cr TDS payable). **Bespoke**.
  - TDS reports: withholding details + computation summary (read‑only, [03](03-financial-reports.md)).
- *Acceptance:* a supplier crossing the threshold has TDS auto‑deducted and posted to the TDS payable account; the TDS report reconciles to that account's balance.

## Engine vs bespoke
- **Engine:** Tax Category, Item Tax Template, Tax Rule, Tax Withholding Category, Tax Template (the
  master itself — though it has a child grid, the *editor* can be engine‑served; the *application* is in the invoice service).
- **Bespoke:** the `taxes_and_totals` engine (inclusive math), TDS deduction posting, tax‑on‑advance.
</content>
