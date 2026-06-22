# Stock Module — Gap Analysis & Phased Implementation Plan

**Scope:** OptiReach ERP Stock module vs ERPNext v15 Stock, with simplification
recommendations where ERPNext is over‑engineered for a real user.
**Verified against code on:** 2026‑06‑17 (models/services/schemas/API/frontend read directly).
**Business context assumed:** appliance trading/distribution (single→few warehouses,
moving‑average costing, serial tracking *may* matter for warranty — flagged where it does).

---

## 0. Plain‑language summary (read this first)

Think of the Stock module as a **bank for goods instead of money**:

- The **Bin** is the account balance (how much of each item sits in each warehouse, and what it's worth).
- The **Stock Ledger Entry (SLE)** is the bank statement — an append‑only list of every in/out movement.
- **Receipts, Deliveries, Stock Entries** are the cheques/deposits that move goods and write to the statement.

**Where we stand:** the *engine* is solid and honest. Goods move, value is tracked
(moving average), and the accounting (perpetual inventory GL) posts correctly and reverses
cleanly on cancel. **What's thin is the surrounding workflow** — there's no way to set an
opening balance or do a physical count without a workaround, no returns, no reorder
automation, and only two reports.

**Where ERPNext is over‑built:** it has ~25 stock doctypes and ~30 settings. A lot of that
(Serial/Batch *Bundle*, Stock Reservation Entry, Putaway, Inventory Dimensions, the repost
queue, Landed Cost *Voucher* as a separate document) adds clicks and concepts that confuse
SMB users. This plan **deliberately copies the value and drops the ceremony** — and calls out
each place we simplify so it's a decision, not an accident.

---

## 1. What the module does today (verified inventory)

### Masters
| Master | Status | Notes |
|---|---|---|
| **Item** | ✅ bespoke service ([stock_masters.py](backend/app/services/stock_masters.py)) | single `stock_uom`, single `barcode`, single `valuation_method`, `brand` as **free text**, single `reorder_level/qty` (not per‑warehouse), one income/expense account. Create + update + list. |
| **Item Group** | ✅ tree (adjacency `parent_item_group_id`, not ltree) | create + list only — **no update/delete API**, not surfaced in UI (greyed "planned"). |
| **Warehouse** | ✅ tree, `warehouse_type` free string, account override | create + list only; UI surfaced. |
| **Price List / Item Price** | ✅ | create + list; Item Price has `valid_from/upto`, currency. |
| **UOM + UOM Conversion** | ✅ exists but **orphaned** ([core/uoms.py](backend/app/api/v1/core/uoms.py), [models/core.py:253](backend/app/models/core.py#L253)) | global UOM master + global from/to conversion table exist, **but nothing in stock uses them** — transaction lines store `uom` as a free string, no per‑item UOM, no `conversion_factor`/`stock_qty`. |

### Ledger & valuation
- **Stock Ledger Entry** — append‑only, DB‑trigger‑protected, single writer ([stock_ledger.py](backend/app/services/stock_ledger.py)).
- **Bin** — maintained per (item, warehouse): `actual_qty, reserved_qty, ordered_qty, valuation_rate, stock_value`. Row‑locked, deadlock‑safe ordering.
- **Moving Average** valuation ✅ (with sensible zero/negative‑crossing reset).
- **Negative stock** blocked unless per‑company `allow_negative_stock` setting.
- **Cancellation** writes mirror entries; **blocks** if stock was since consumed at a different valuation (honest, but a dead‑end without Stock Reconciliation — see Gap #1).

### Transactions
| Doc | Status | Stock effect | GL on submit |
|---|---|---|---|
| **Stock Entry** | ✅ Receipt / Issue / Transfer only | SLE in/out/transfer at moving‑avg | Dr/Cr inventory ↔ Stock Adjustment |
| **Material Request** | ✅ Purchase / Transfer / Issue | none (demand only) | none |
| **Purchase Receipt** | ✅ | SLE in at receipt rate; updates `last_purchase_rate` | Dr inventory / Cr Stock Received But Not Billed |
| **Delivery Note** | ✅ | SLE out at moving‑avg; releases `reserved_qty` | Dr COGS / Cr inventory (revenue posts on invoice — correct) |

PO→PR and SO→DN linkage works (received/delivered qty accrue, status rolls up).

### Reports
- **Stock Balance** (current, from Bin) and **Stock Ledger** (chronological). That's it.

---

## 2. Gap analysis vs ERPNext v15 Stock

Legend: 🔴 missing · 🟡 partial · 🟢 present · **P=priority** (1 highest)

### 2.1 Functional gaps that block real‑world use
| # | Gap | State | P | Why it matters |
|---|---|---|---|---|
| **1** | **Stock Reconciliation** (opening stock + physical count) | 🔴 | **1** | Today the *only* way to set opening balances or fix a count is a Material‑Receipt Stock Entry hack. Also the **only correct escape hatch** when a cancellation is blocked by changed valuation. Foundational. |
| **2** | **Returns** (DN return / PR return / debit‑credit note linkage) | 🔴 | **1** | No way to take goods back into stock or send back to supplier. Appliances = high return rate. |
| **3** | **Reorder automation** | 🟡 fields exist, unused | **2** | `reorder_level`/`reorder_qty` are stored but **nothing consumes them** — no job creates Material Requests. Dead data. |
| **4** | **Historical / projected stock reports** | 🔴 | **2** | Stock Balance is *current only*. No balance‑as‑on‑date, projected qty, ageing, or shortage report. Auditors and planners need these. |
| **5** | **Landed cost** (freight/customs into valuation) | 🔴 | **3** | Imported appliances carry duty/freight; without it COGS is understated. (We'll do this the *simple* way — see §3.) |
| **6** | **Multi‑UOM at item level** (buy in Box, stock in Nos) | 🔴 | **3** | UOM master exists but unwired; lines have no `conversion_factor`/`stock_qty`. |
| **7** | **PR accepted/rejected split** | 🔴 | 4 | Single `qty` only. Optional for SMB; matters for QC‑heavy receiving. |

### 2.2 Master/data‑model gaps
| Gap | State | P | Note / simplification stance |
|---|---|---|---|
| **Item engine descriptor + full master UI** | 🟡 bespoke `/items`, Item Group/Price List greyed | 2 | Surface the masters that already work; consider engine‑migrating Item. |
| **Brand as a master** | 🟡 free text | 4 | Keep free text unless reporting needs it — a master adds a click for little gain. |
| **Item‑level UOM conversion table** | 🔴 | 3 | Needed for Gap #6. |
| **Batch** | 🔴 | 3* | *Elevate for appliances if lot/expiry tracking is required.* |
| **Serial No** | 🔴 | 2–3* | *Appliances often need serials for warranty/RMA — may be higher priority than generic SMB.* |
| **Item variants / attributes** | 🔴 | low | **Recommend NOT building** the attribute engine — model variants as plain Items (see §3.1). |
| **Item Manufacturer, Item Alternative, Customs Tariff, Inventory Dimension, Putaway Rule** | 🔴 | low | Mostly skip/defer (see §3). |
| **Stock Settings doctype** | 🟡 one `SystemSetting` key | 4 | Consolidate the 4–5 settings that matter; don't replicate ERPNext's ~30. |

### 2.3 Valuation / engine gaps
| Gap | State | Stance |
|---|---|---|
| **FIFO valuation** | 🔴 (column reserved, raises error) | Build only if a customer demands it; Moving Average covers most. |
| **LIFO** | 🔴 | **Do not build** — disallowed under IFRS/Ind‑AS. |
| **Back‑dated repost engine** | 🔴 by design (insertion‑order only) | **Keep it out** — see §3.4. Forbid back‑dating; use Stock Reconciliation for corrections. |
| **Batch/Serial valuation** | 🔴 | Only with Gap batch/serial. |

### 2.4 Logistics / advanced (mostly simplify‑away)
Pick List, Packing Slip, Shipment, Stock Reservation Entry, Quality Inspection, Repost Item
Valuation, Closing Stock Balance — all 🔴. See §3 for which to fold‑in vs drop.

---

## 3. Where ERPNext is over‑engineered → how we simplify

The user POV test: *can a non‑accountant warehouse clerk do this without training?* Each item
below is a deliberate "copy the value, drop the ceremony" decision.

### 3.1 Item variants & attributes → **plain Items**
ERPNext: a "template" Item + Item Attributes + an attribute matrix generating variant Items.
Powerful for apparel, baffling for everyone else.
**Simplify:** model each sellable thing as its own Item with a shared Item Group and a naming
convention (`AC‑1.5T‑INV`, `AC‑1.5T‑STD`). Skip the attribute engine entirely until a vertical
demands it. *Saves an entire doctype family and a confusing UI.*

### 3.2 Landed Cost Voucher → **charges on the Purchase Receipt**
ERPNext: create a *separate* Landed Cost Voucher, re‑select the receipts, type freight/customs,
let it re‑value. Two documents, easy to forget the second.
**Simplify:** add an "Additional Costs" section (freight, customs, insurance) directly on the
Purchase Receipt; apportion by amount/qty into incoming valuation at submit. **One document.**

### 3.3 Serial & Batch *Bundle* (v15) → **inline fields**
ERPNext v15 moved serial/batch entry into a separate "Serial and Batch Bundle" doctype opened in
a dialog — widely disliked as extra clicks.
**Simplify (when we do batch/serial):** keep `batch_no` and a `serial_nos` text field **inline on
the item row**, like ERPNext ≤v13. Validate against masters; no bundle doctype.

### 3.4 Repost Item Valuation queue → **no back‑dating**
ERPNext lets you post stock in the past, then runs a heavy background "repost" that recomputes all
later entries and can lock the system. Conceptually hard, operationally scary.
**Simplify:** **forbid back‑dated stock postings** (post date ≥ last movement). Corrections go
through Stock Reconciliation (Gap #1). This is what the code *already* assumes — we make it an
explicit, documented rule instead of a latent risk. *Removes the single most complex subsystem.*

### 3.5 Stock Reservation Entry (v15) → **soft reserve on Bin**
ERPNext v15 added a whole reservation doctype with enable flags and serial/batch reservation.
**Simplify:** we already maintain `reserved_qty` on the Bin straight from Sales Orders. Keep that
soft reservation; **don't** build the SRE doctype.

### 3.6 Pick List / Packing Slip / Shipment → **fold into Delivery Note**
Three logistics documents for what an SMB does in one step.
**Simplify:** the Delivery Note (warehouse + qty + optional package note) is enough. Add a Pick
List later *only* if multi‑bin warehouse picking becomes real.

### 3.7 Quality Inspection templates → **pass/fail + remarks**
ERPNext: QI Template + Parameters + readings per receipt.
**Simplify:** an optional `quality_status` (Accepted/Rejected) + `inspection_remarks` on the
receipt row. Add structured templates only for regulated verticals.

### 3.8 Stock Entry's 8 purposes → **keep 3**
Manufacture, Repack, Subcontract, Material‑Consumption/Transfer‑for‑Manufacture belong to a
Manufacturing module. **Keep Receipt/Issue/Transfer**; the rest arrive only if Manufacturing does.

### 3.9 Valuation methods → **Moving Average is the default, FIFO on request**
Per‑item method switching confuses accountants and breaks comparability.
**Simplify:** one company‑wide method (Moving Average). Expose FIFO only if needed; never LIFO.

### 3.10 Stock Settings (~30 toggles) → **5 that matter**
Default valuation method, allow negative stock, default warehouse, auto‑insert item price on
receipt, and (optional) freeze‑stock‑before‑date. Hardcode sane defaults for the rest.

> **Net effect:** of ERPNext's ~25 stock doctypes, this plan builds ~6 net‑new (Stock
> Reconciliation, returns reuse existing docs, optional Batch/Serial) and **consciously skips ~10**.

---

## 4. Phased implementation plan

Ordering mirrors the proven `_parity_plan_synthesis.md` philosophy: **zero/low‑migration,
high‑visibility wins first; correctness‑risk and new‑subsystem work later, each independently
testable.** Every phase ends with a Playwright‑verifiable check ([playwright‑ui‑loop]).

### Phase 0 — Surface what already exists *(days, near‑zero risk)*
Make the module *look* as complete as it already is.
- ✅ **Item (Products & Services) full master UI (2026‑06‑18):** new `ItemFormView.vue` for create +
  view/edit with ERPNext‑style sections (Details / Inventory / Selling / Purchasing) exposing every
  field the backend already accepted — **reorder level/qty**, lead time, valuation method, UOM (from
  the UOM master), default warehouse, income/expense accounts, flags, brand, barcode — plus a live
  per‑warehouse **stock summary** on the detail page. Routes `/items/new` + `/items/:id`; list rows
  link in; old cramped inline form removed. `ItemUpdate`‑immutable fields (code/UOM/flags/valuation
  method) are read‑only on edit. Verified: full create+patch roundtrip, vue‑tsc clean, `:8080` rebuilt.
- Still TODO: un‑grey **Item Group, Price List, Item Price, Brand** master pages; add **update/delete**
  to Item Group & Warehouse (services are create+list only today).

### Phase 1 — Stock Reconciliation *(the #1 functional gap)* ✅ DONE (2026-06-18, migration 0028)
New doctype `Stock Reconciliation` + service writing SLEs for the qty/value *difference* vs current
Bin, and GL to the Stock Adjustment account. Two modes (label only): **Opening Stock** and
**Stock Reconciliation** (physical count).
- New ledger writer `make_reconciliation_entries` posts an **absolute** target qty+rate (overrides
  moving average); cancellation reuses the existing `make_reverse_sl_entries` mirror path.
- **Unblocks** the cancellation dead‑end (§1) — the documented corrective action.
- **Migration 0028:** tables `stock_reconciliations` + `stock_reconciliation_items`; parent RLS'd;
  partial (company_id, docstatus) index.
- Backend: model + schema + `services/stock_reconciliation.py` + `/stock-reconciliations` CRUD/submit/cancel.
  Frontend: `StockReconciliationView.vue` (book‑vs‑counted grid) + route + Stock workspace nav.
  Permissions seeded (Stock Manager all / Stock User no‑cancel); demo physical‑count added to seed_demo.
- **Verified:** integration test `test_stock_reconciliation` (shortage → Dr Stock Adjustment, pure
  revaluation, cancel restores bin, GL balanced); full suite 87 passed; ruff + vue‑tsc clean;
  migration applied to head; live API smoke created `MAT-RECO-2026-00001`.

### Phase 2 — Reorder automation + planning reports *(high value, additive)* ✅ DONE (2026-06-18, no migration)
- **Reorder / shortage report + one‑click MR:** `GET /stock-reorder` lists items whose company‑wide
  projected qty (on‑hand + on‑order − reserved) is below `reorder_level`; `POST /stock-reorder/material-request`
  drafts a Purchase Material Request for the shortfall (`reorder_qty`). Makes the dormant fields live.
  Frontend `ReorderView.vue` (checkbox select + Create) → redirects to MR list with a confirmation banner.
- **Stock Balance as‑on‑date:** `GET /reports/stock-balance?as_of=` — historical snapshot via a
  deterministic **SUM(actual_qty)/SUM(stock_value_difference)** aggregation of the ledger (on‑hand only;
  reserved/ordered are live‑only).
- **Stock Ageing:** `GET /reports/stock-ageing` — FIFO replay into 0‑30/31‑60/61‑90/90+ buckets +
  avg age + value. Surfaced as a third tab on the Stock Balance page.
- Nav: Reorder + Stock Ageing added to Stock workspace sidebar/cards; `as_of` input + Ageing tab on the report page.
- **Adversarial review run; all confirmed findings fixed:** (1) HIGH — ageing now handles cancellations
  by removing the cancelled receipt's own lot (voucher‑id matched), not the oldest; (2) MEDIUM — as‑on‑date
  uses SUM aggregation so a multi‑line same‑item voucher can't skew it; (3) MEDIUM — reorder MR now rejects
  items with no default warehouse instead of writing a null‑warehouse line; (4) MEDIUM — Stock Balance tabs
  are URL‑driven (no dead sidebar tab links); (5) low/nits — stale‑row flash, avg‑age rounding, as‑of caption
  on Ageing, MR “created” banner. Tenant‑isolation/permissions reviewed clean.
- **Verified:** integration tests `test_reorder_and_planning_reports` + `test_stock_report_edge_cases`
  (ageing‑cancel + as‑of multi‑line); full suite **88 passed**; ruff + vue‑tsc clean; `:8080` rebuilt.

### Phase 3 — Receipt/Delivery depth: returns + landed cost + rejected split ✅ DONE (2026-06-18, migrations 0031–0033)
Shipped in three independently-verifiable sub-phases (3A → 3B → 3C). Coordinates with selling/buying
parity **Tranche 6**. Throughout, DN/PR still post **only stock + COGS/SRBNB GL — never tax/revenue**
(that stays on the invoice); returns mirror this exactly.

- **3A — Returns (DN + PR), migration 0031.** `is_return` + `return_against_id` (self-FK) on both docs
  (+ `supplier_delivery_note` on PR). A return keeps **positive** line qty and branches on `is_return`
  (a signed qty would break the `DN_BILLING`/`PR_BILLING` caps). The GL needs **no** branching: a DN
  return posts an SLE **in** and a PR return an SLE **out**, so the existing value flips negative and
  `make_gl_entries`' negative-normalisation auto-swaps Dr/Cr (COGS / SRBNB reversed); cancel reuses the
  generic reverse paths. **DN returns re-enter at the original delivery's value-out rate**
  (`stock_value_difference / actual_qty`, NOT the entry's `valuation_rate` — that is 0 when the delivery
  emptied the bin), so COGS reverses correctly even when the bin is empty at return time. **PR returns
  likewise value the stock-out at the original receipt rate** (same shared `voucher_unit_rates` helper +
  an `outgoing_rate` override on the SLE writer), so the SRBNB reversal is exact even after the moving
  average drifted; removing at a rate other than the average reprices the remaining stock, and the writer
  falls back to the current average if posting at the original rate would drive the bin value negative (a
  rare prior write-down below the receipt cost). Returns
  net `delivered_qty`/`received_qty` back down (sign-aware), don't touch `reserved_qty`/`ordered_qty`/
  `last_purchase_rate`, and don't over-return (per item+warehouse vs the original; cumulative netting via
  the SO/PO cap when linked). Status → `Completed`. Frontend: "Is Return" checkbox + return-against
  picker on both forms, `?return_against=` prefill, and a **Make Return** button on the submitted-doc
  detail view.
- **3B — Accepted/rejected split on PR, migration 0032.** `rejected_qty` + `rejected_warehouse_id` on
  the receipt line; `qty` stays the accepted qty. Submit posts a second SLE-in for rejected → rejected
  warehouse (valued, Dr inventory / Cr SRBNB); **PO `received_qty` and the ordered-qty release count
  `qty + rejected_qty`** so a partly-rejected receipt still closes the order; billing stays on accepted
  qty. Rejected qty is barred on returns. Frontend grid gains Rejected Qty / Rejected WH columns
  (hidden in return mode); detail shows a Rejected column when present.
- **3C — Landed cost as PR charges, migration 0033.** New `purchase_receipt_charges` child table
  (freight/customs/insurance). On submit the charge total apportions **by item base value** into the
  accepted lines' incoming rate (rejected lines get none; last row absorbs the rounding remainder so
  shares sum exactly). GL splits the credit: **Cr SRBNB = item base, Cr each charge account = its
  amount** (Dr inventory base+charges balances exactly). One document, no separate Landed Cost Voucher
  (§3.2). Frontend: an "Additional Costs" section on the PR form.
- **Adversarial review found + fixed one HIGH bug:** the DN-return rate lookup originally used the
  out-entry's `valuation_rate`, which is 0 when the delivery emptied the bin — a return would then
  re-enter at the item-master default and COGS would not reverse. Switched to value-out/qty-out (the
  shared `voucher_unit_rates` helper); added `test_delivery_note_return_after_full_delivery` to lock it in.
- **Follow-up — PR returns also pin to the original receipt rate** (2026-06-18): added an `outgoing_rate`
  override to the SLE writer so a PR return values its stock-out at the original receipt rate (drift-exact
  SRBNB reversal), repricing the remaining stock; falls back to the moving average if that would drive the
  bin negative. Tests `test_purchase_receipt_return_drift` (10@100 + 10@140, return 3 → SRBNB −300 not −360)
  and `test_purchase_receipt_return_below_average_falls_back` (write-down → graceful fallback) added.
- **Verified:** integration tests `test_delivery_note_return`, `test_delivery_note_return_after_full_delivery`,
  `test_purchase_receipt_return`, `test_purchase_receipt_return_drift`,
  `test_purchase_receipt_return_below_average_falls_back`, `test_purchase_receipt_rejected_split`,
  `test_purchase_receipt_landed_cost` (deliver 10 → return 3 → Bin +3 / COGS reversed 900 / SO
  `delivered_qty` 7; empty-bin + drift returns reverse at the original rate; rejected split into two bins;
  freight folds to a 120/unit landed rate). Full suite **96 passed**; ruff + vue-tsc clean; migrations
  0031–0033 apply + downgrade roundtrip cleanly to a single head; `seed_demo` Phase 3 block runs end-to-end;
  Playwright UI smoke confirmed the PR form (rejected columns, landed-cost section, return toggle) and the
  DN **Make Return** flow (created + submitted a live sales return).

### Phase 4 — Multi‑UOM at item level ✅ DONE (2026-06-18, migration 0034)
Buy in Box, stock/sell in Nos. **Conversion model = flat fields on the Item** (no child table);
**scope = full buy/sell cycle**, shipped in three sub-phases. Core invariant: every line carries
`conversion_factor` + **`stock_qty = qty × conversion_factor`**, and everything touching the Bin,
demand counters or cross-document caps uses `stock_qty` — never `qty`. Amounts/rates stay in the
transaction UOM; **currency `conversion_rate` is strictly separate** from the UOM factor. An SLE
posts `actual_qty = ±stock_qty` and `incoming_rate = (row base value) ÷ stock_qty`, so the value
added always equals `base_amount` and valuation stays per stock UOM. The factor is resolved
**server-side** (`resolve_conversion_factor`, [stock_common.py](backend/app/services/stock_common.py))
from the item — an undefined UOM is rejected (strict) on stock/order docs, lenient (→1) on invoices.

- **Migration 0034:** `purchase_uom`/`sales_uom` + factors on `items`; `conversion_factor` + `stock_qty`
  on **all ten** transaction-line tables (the six InvoiceItemMixin lines — quotation, supplier
  quotation, PO, SO, SI, PI — plus PR/DN/stock-entry/material-request), `stock_qty` backfilled to `qty`.
- **4A — masters + stock docs + the whole backend invariant.** Item UOM fields (form + schema +
  service); PR/DN/Stock-Entry/MR resolve the factor and move the Bin/SLE by `stock_qty` with
  per-stock-unit incoming rates; PO `ordered_qty` / SO `reserved_qty` / MR `per_ordered` and the MR→PO
  link all switch to stock units; **`cycle_links` `SO_DELIVERY` + `PO_RECEIPT` caps switch to `stock_qty`**
  (billing caps stay document qty/amount). Frontend: Item form purchase/sales UOM + factor; `ItemsGrid`
  gains a per-row UOM select + a read-only Stock-Qty column; PR/DN forms wired (default to the buy/sell
  UOM, scale the resolved rate, show stock_qty). (Stock-Entry/MR *UI* UOM deferred — custom forms,
  stock-UOM by default; backend ready.)
- **4B — orders.** PO/SO already resolve the factor (4A backend); `OrderFormView` gets the UOM select +
  Stock-Qty column, and the inline Create-Receipt/Delivery pending math now nets in stock units.
- **4C — invoices.** SI/PI populate `stock_qty` (informational — invoices don't touch the Bin and bill
  on document qty/amount), lenient factor; `InvoiceFormView` shows a Stock-Qty column and defaults the
  buy/sell UOM. Free-text invoice lines keep an editable UOM.
- **Migration bug caught + fixed mid-build:** `quotation_items`/`supplier_quotation_items` also use
  `InvoiceItemMixin` and were initially omitted from 0034 — tests passed (create_all builds from models)
  but a fresh alembic DB would have failed; added them and reconciled the dev DB.
- **Verify:** 6 integration tests — PR 5 Box (factor 12) → Bin **60, not 5**, valuation **100/Nos**, PO
  `received_qty` 60; DN 5 Box → Bin −60, COGS at stock rate, SO `delivered_qty` 60; Stock-Entry in Box;
  undefined-UOM → 422; PO/SO in Box accrue `ordered_qty`/`reserved_qty` 60; Box sales invoice carries
  `stock_qty` 60 and bills on amount. Full suite **101 passed**; ruff + vue-tsc clean; migration 0034
  applies + downgrade roundtrip on a fresh DB; `seed_demo` (with a Box-of-25 carton item) runs end-to-end.

### Phase 5 — Batch & Serial ✅ DONE (2026-06-19, migrations 0035–0036)
Simplified inline model (§3.3): the transaction **line** is the source of truth for which serials /
which batch a voucher touched; lightweight masters hold the rest. Valuation stays **Moving Average** —
serials/batches are a tracking layer, never separate valuation. Shipped in two sub-phases.

**5A — Serial No** (`0035_serial_no`): `items.has_serial_no`; new `serial_nos` master (status **In Stock
/ Delivered / Returned** + warehouse + warranty, RLS, unique `(company_id, serial_no)`); inline
`serial_nos` text on PR / DN / Stock-Entry lines. Single lifecycle service `stock_serials.py` hooked
**after `make_sl_entries`** in submit, symmetric revert in cancel. **Count rule:** a serialised line lists
exactly **`stock_qty`** serials (= qty × conversion_factor — composes with Phase 4 multi-UOM), not `qty`.
Per-row "Serials (n/req)" dialog on the PR/DN forms; read-only Serial No list view.
- Transitions: receipt → create In Stock · delivery → Delivered · issue → Returned · transfer → re-home ·
  DN return → In Stock · PR return → Returned · receipt-cancel → delete (blocked if since moved on).
- **Returns are bound to the original document:** a DN return only restocks serials the *original* DN
  shipped (`delivery_voucher_match=return_against_id`, clears the stale link); a PR return only sends back
  serials received on the *original* receipt (`purchase_voucher_match`). Cancels are true inverses
  (re-link + warehouse guard). Receipt-cancel `delete_serials` also guards the warehouse so a
  transferred-away unit can't be deleted. Duplicate-serial across lines/items raises a clean 422 (flush +
  company-wide existence check). `has_serial_no`/`has_batch_no` can't be toggled while stock is on hand.
  *(All six findings from an adversarial static-analysis review were fixed and regression-tested.)*

**5B — Batch** (`0036_batch_no`): `items.has_batch_no`; new **descriptor-backed** `batches` master
(`/m/batch`: batch_no + item + optional `expiry_date` + disabled, RLS, unique `(company_id, batch_no)`);
inline `batch_no` on the three lines. A batch is a **label** (no per-unit status, no SLE impact).
`stock_batches.py` validates a batched line names an existing, enabled batch **of that item**; a
non-batched item must not carry one; **shipping an expired batch out (customer delivery / pure issue) is
blocked** (receipts, internal transfers and returns are not). The gate runs at build time **and again at
submit** — the authoritative check, since the Batch master is mutable between draft and submit. Per-row
Batch dropdown (populated per-item from `/registry/batch`) on PR/DN forms; Batch column on the document
view.
- *An adversarial static-analysis review confirmed 12 findings; all material ones fixed + regression-tested:*
  the **HIGH** was that the expiry/enabled gate was create-only — a batch disabled, expired, deleted, or
  re-pointed between draft and submit would still ship; now every submit (PR/DN/SE) re-validates against the
  live master. Batch master hooks block batching a non-batch item, re-pointing/renaming an in-use batch, and
  deleting a referenced batch; the `has_serial_no`/`has_batch_no` toggle guard counts non-zero bins (not a
  net SUM); batch uniqueness is per `(company, item, batch_no)` so two SKUs can share a lot string.

- **Verified:** 111 backend tests green (incl. serial lifecycle, count-uses-stock_qty, return-binding,
  duplicate-serial 422, toggle guard; batch lifecycle, foreign/missing-batch 422, expiry-blocks-delivery);
  `ruff` clean; `vue-tsc` clean; migrations 0035→0036 apply + downgrade roundtrip on a fresh DB (single
  head `0036_batch_no`). Playwright UI smoke (both sub-phases): flag an item serialised → receive 3 via a
  PR (dialog 3/3) → Serial list shows 3 In Stock → deliver 1 → Delivered → second delivery of that serial
  rejected; flag an item batched → create a Batch (expiry) → receive against it (batch dropdown) → Batch
  column shows the lot.

### Phase 6 — FIFO + lightweight back‑dating *(defer unless required)*
FIFO queue valuation and a minimal repost only if a customer needs back‑dated entries. Highest
complexity, lowest near‑term value. Default: **don't build** (§3.4).

---

## 5. Correctness notes carried from the current code (don't regress these)
- **Single SLE/Bin writer**, row‑locked, canonical lock order — preserve when adding reconciliation/returns.
- **Cancellation honesty:** blocking a cancel when valuation moved is *correct*; Phase 1 gives it the missing escape hatch.
- **DN/PR post no taxes by design** — taxes/revenue belong to the invoice; returns must respect this.
- **Zero‑rate receipts** fall back to price‑list/last‑purchase/valuation rate to avoid diluting the moving average — keep.

## 6. Open questions to confirm before Phase 1
1. **Serial tracking priority** — given appliances, do you need serial/warranty tracking sooner (bump Phase 5 ahead of 4)?
2. **Single vs multi‑warehouse** — does any customer run multi‑bin picking (affects Pick List / §3.6)?
3. **Imports** — are landed costs (duty/freight) in scope now (Phase 3) or later?
4. **Back‑dating** — is forbidding back‑dated stock entries (§3.4) acceptable as policy? It removes the most complex subsystem.
