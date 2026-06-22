# Assets Module — Build Plan (ERPNext-style Fixed Asset Management)

**Scope:** a new top-level **Assets** module for OptiReach ERP, modelled on ERPNext v15 Assets, with
MSME simplifications (single appliance-distribution company, India GAAP, no multi-finance-book).
**Status:** 🔴 greenfield — **zero asset code today** (the "asset" hits in the repo are just Chart-of-Accounts
asset *accounts* + report sections). This is a build plan, not a gap analysis.
**Designed:** 2026-06-22.

> Mirrors the structure of [ACCOUNTING_GAP_AND_PLAN.md](ACCOUNTING_GAP_AND_PLAN.md): plain-language
> summary → what ERPNext provides → what we simplify → data model → the depreciation engine → GL
> integration → phased plan → scope cuts. **House rule:** masters/config are **engine-served**
> (`DocTypeDescriptor`); anything that **posts to the GL** is a **hand-written service** behind the
> engine's form/list boundary (see [ENGINE_GUIDE.md](ENGINE_GUIDE.md)).

---

## 0. Plain-language summary (read this first)

A **fixed asset** is something you buy to *use* for years — a delivery van, a forklift, machinery,
computers — not something you resell. Accounting rules say you can't treat its whole cost as an expense
the day you buy it; instead you spread that cost across the years you use it. That yearly "wearing out"
is **depreciation**.

Analogy: you buy a ₹60,000 phone you'll use for 5 years. Rather than show a ₹60,000 hit in month one,
the books show it "using up" ~₹1,000 of value each month. After 3 years it's worth ~₹24,000 on paper
(its **book value**). The Assets module does exactly this, automatically, for every asset:

- keeps a **register** of each asset (what it cost, when bought, where it is, who holds it),
- **auto-books depreciation** every month/year into the ledger (a scheduled job),
- tracks **moving, maintaining, repairing** an asset, and
- handles **selling or scrapping** it — working out the profit or loss vs its book value.

**Where we stand:** the *accounting foundation already exists* — the Chart of Accounts ships a **Fixed
Assets** group, **Accumulated Depreciation**, a **Depreciation** expense account, and **Gain/Loss on
Asset Disposal**. We also already have an immutable **GL**, a **Journal Entry** service, and an
**APScheduler** job registry. So Assets is mostly: a few masters + an asset document + a **depreciation
schedule generator** + a **scheduled posting job** that all *reuse* the existing GL/JE — **no new
posting engine, no new accounts**.

---

## 1. What ERPNext provides

| DocType | Purpose |
|---|---|
| **Asset Category** | Defaults for a class of assets: depreciation method, useful life, and the 3 GL accounts (fixed-asset, depreciation-expense, accumulated-depreciation). |
| **Asset** | One fixed asset: gross purchase value, available-for-use date, location, custodian, status, and its depreciation schedule. |
| **Asset Depreciation Schedule** | The planned periodic write-downs (date + amount + posted flag) over the asset's life. |
| **Asset Movement** | Transfer an asset between locations / custodians. |
| **Asset Maintenance** + **Maintenance Log** | Preventive-maintenance schedule and completion log. |
| **Asset Repair** | Breakdown repair record (cost, downtime, optional capitalisation). |
| **Asset Value Adjustment** | Revalue an asset (impairment / write-up). |
| **Asset Capitalization** | Combine stock items + costs into a new asset. |
| **Asset Disposal** | Sell (via Sales Invoice) or scrap; books gain/loss vs book value. |
| **Location** | Where an asset physically sits (tree). |
| Reports | Asset Depreciation Ledger, Asset-wise depreciation, Fixed Asset Register (net block). |

**Depreciation methods:** Straight Line, Written Down Value (declining balance), Double Declining, Manual.

---

## 2. Where ERPNext is over-engineered → how we simplify

The POV test: *can a 20-person appliance distributor track their vans, machinery and computers and get
correct depreciation, without hiring a Frappe consultant?*

| ERPNext feature | Decision |
|---|---|
| **Multiple Finance Books** (parallel depreciation schedules per book) | **Single book.** One schedule per asset. (Same call as accounting §3.2.) |
| **Asset Capitalization** (merge items/costs into an asset) | **Defer.** Create assets directly or from a purchase line; capitalisation is niche. |
| **Shift-based depreciation, component accounting** | **Skip.** Rarely needed at this scale. |
| **Elaborate maintenance teams/tasks/SLAs** | **Lean:** a simple maintenance log + repair record with a cost. Drop the team/task machinery. |
| **Asset serial-number / batch-style component tracking** | **Skip.** One Asset = one tracked unit. |
| Auto-creation of N assets from a multi-qty purchase line | **Lean:** create one Asset per line; offer a "quantity" only if asked. |
| Deferred-revenue-style schedule reposting / bisect tools | **Skip** (same anti-ceremony stance as accounting §3.3). |

Everything above is **explicitly out of scope** unless a future requirement reverses it.

---

## 3. Data model (engine-served vs bespoke)

**Engine masters** (recipe card → free list/form/permissions):
- **Asset Category** — `category_name, depreciation_method (Straight Line | Written Down Value | Manual),
  useful_life_months (Int), salvage_value_percent (Float), fixed_asset_account, depreciation_expense_account,
  accumulated_depreciation_account (Link account ×3), disabled`.
- **Location** — a flat or tree master (`location_name`, optional parent) for where assets sit. (Could
  reuse the existing Cost Center / Warehouse tree, but a dedicated lightweight Location is cleaner.)
- **Asset Maintenance** / **Asset Repair** — lean records (asset, date, description, cost, status). Repair
  can optionally raise a JE (Dr Repair Expense / Cr Bank) but keep that a normal JE, not coupled.

**Bespoke documents** (form/list from the engine, calculations hand-coded — anything touching GL):
- **Asset** — gross_purchase_amount, purchase_date, available_for_use_date, asset_category, location,
  custodian, status (Draft | Submitted | Partially Depreciated | Fully Depreciated | Sold | Scrapped),
  + a **depreciation schedule** child (period_date, amount, accumulated, posted flag, journal_entry_id).
- **Asset Movement** — light doc: asset, from/to location + custodian, date. (No GL.)
- **Asset Disposal** — sell or scrap: removes cost + accumulated dep, books **Gain/Loss on Asset Disposal**.
- **Asset Value Adjustment** — revalue: posts the difference to a JE; reschedules remaining depreciation.

**Decision rule (same as accounting §6):** posts to GL or runs depreciation math → **bespoke service**;
pure reference/config → **engine descriptor**; report → **read-only endpoint**.

---

## 4. The depreciation engine (the heart)

On Asset **submit** (status → Submitted, from `available_for_use_date`), generate the schedule:
- **Straight Line:** per-period = `(gross − salvage) / useful_life_periods`. Equal amounts; last period
  absorbs rounding so total = depreciable base exactly.
- **Written Down Value (declining balance):** per-period = `rate% × opening book value`, where the rate
  derives from useful life (ERPNext: `1 − (salvage/gross) ** (1/life)`), never depreciating below salvage.
- **Manual:** user enters the rows.
- `book_value = gross − accumulated_depreciation`; salvage is the floor.

A **scheduled job** (`app/jobs/assets.py::process_depreciation`, registered in `SCHEDULED_JOBS`,
daily ~03:00 — same mechanism as the planned Subscription job) finds schedule rows due (`period_date <=
today`, not yet posted) **across all companies** and for each posts a JE via the existing
`gl.make_gl_entries` / Journal Entry service:

```
Dr  Depreciation Expense        (per the Asset Category)
Cr  Accumulated Depreciation    (per the Asset Category)
```

then marks the row posted + links the JE, and flips the asset to Fully Depreciated on the last row.
**Idempotent:** a posted row is never reposted (guard on the posted flag, set in the same transaction as
the JE) — a re-run can't double-book. Cancelling depreciation = reverse the JE + clear the flag (the GL
stays append-only via reversing entries, per accounting §5).

A **manual "depreciate now"** endpoint triggers the same per-asset routine — essential for testing
without waiting for cron, and for catch-up runs.

---

## 5. GL integration (reuse what exists — no new accounts, no new posting engine)

| Event | GL posting | Accounts (already in the COA) |
|---|---|---|
| **Acquire** | Dr Fixed Asset / Cr Bank or Payable | Fixed Assets group; via a **Purchase Invoice** (is_fixed_asset item) or a manual JE |
| **Depreciate** (periodic) | Dr Depreciation Expense / Cr Accumulated Depreciation | Depreciation; Accumulated Depreciations |
| **Dispose — sell** | remove cost + accum. dep; Dr Bank/Receivable (proceeds); Dr/Cr Gain or Loss | Gain/Loss on Asset Disposal |
| **Dispose — scrap** | remove cost + accum. dep; Loss = remaining book value | Gain/Loss on Asset Disposal |
| **Value adjustment** | Dr/Cr the change vs Accumulated Depreciation / a revaluation account | (configurable) |

All postings go through the existing **Journal Entry** service / `gl.make_gl_entries` — the Assets module
*drives* postings, it never re-implements them (same principle as Subscription driving Sales Invoice).

**Purchase integration:** add `is_fixed_asset` + `asset_category_id` to **Item**. A Purchase
Invoice/Receipt line for such an item debits the fixed-asset account and can **auto-create a draft Asset**
to be completed. *MSME-lean:* ship **manual asset creation first**; auto-from-purchase in a later phase.

---

## 6. Phased build plan

### Phase 1 — Asset register + straight-line depreciation *(the gating core)*
- **Asset Category** (engine master) + **Location** (engine master) + `is_fixed_asset`/`asset_category` on Item.
- **Asset** bespoke doc: create/submit/cancel; schedule generation (Straight Line + Manual); book value.
- **`process_depreciation`** scheduled job (Dr Depreciation / Cr Accum. Dep.), idempotent, + a manual
  "depreciate now" endpoint.
- Acquisition via a manual JE or a fixed-asset Purchase Invoice line.
- Frontend: Asset Category/Location engine forms; a bespoke Asset list+detail (with the schedule + book value).
- *Acceptance:* a ₹120k asset, 60-month SL life, ₹0 salvage → 60 monthly entries of ₹2,000; book value
  declines correctly; the job never double-posts; asset flips to Fully Depreciated on the final row.

### Phase 2 — Disposal + movement + WDV
- **Asset Disposal** (sell/scrap → gain/loss JE, stops depreciation), **Asset Movement** (location/custodian),
  and the **Written Down Value** method.
- *Acceptance:* disposing the Phase-1 asset after 24 months at ₹50k books the correct gain/loss vs its
  ₹72k book value and halts further depreciation.

### Phase 3 — Maintenance, repair, value adjustment, auto-from-purchase
- **Asset Maintenance** + **Asset Repair** (lean logs; repair can raise a normal JE), **Asset Value
  Adjustment** (revalue + reschedule), and **auto-create Asset from a fixed-asset Purchase Invoice line**.

### Phase 4 — Reports
- **Fixed Asset Register / Net Block** (gross, accumulated dep, book value per asset/category),
  **Asset Depreciation Ledger** (posted entries), **Asset-wise depreciation** schedule — read-only
  endpoints + a Reports surface (its own module reports view or tabs).

---

## 7. Scheduling
Reuse the existing **APScheduler** registry (`app/core/scheduler.py` → `SCHEDULED_JOBS`). The
`process_depreciation` job is the asset analogue of the planned `process_subscription` job: a daily,
idempotent, cross-company sweep that posts due schedule rows as system-actor JEs. No new infra.

## 8. Engine vs bespoke (summary)
- **Engine-served:** Asset Category, Location, Asset Maintenance, Asset Repair.
- **Bespoke services (GL/maths):** Asset (+ schedule), Asset Disposal, Asset Value Adjustment, the
  `process_depreciation` job. **Reports:** read-only endpoints.

## 9. Scope decisions (deliberate cuts)
Single finance book · no capitalization tool (v1) · no component/shift depreciation · lean
maintenance/repair (no teams/tasks) · manual-or-purchase acquisition · reuse JE/GL + scheduler · India
GAAP straight-line + WDV only. Each is a "copy the value, drop the ceremony" call — revisit only on a real
requirement.

---

## 10. Open questions for the owner (answer before Phase 1)
1. **Depreciation cadence** — monthly (typical for management accounts) or annual (statutory minimum)? (Plan assumes monthly, configurable.)
2. **Method** — Straight Line (simple, common) and/or Written Down Value (India Companies Act / IT Act often uses WDV)? (Plan ships SL first, WDV in Phase 2.)
3. **Acquisition path** — do assets mostly arrive via **Purchase Invoices** (then auto-create-from-PI is worth Phase-1) or are they entered manually? (Plan defaults to manual first.)
4. **Asset tagging/barcodes, custodian sign-off, insurance tracking** — needed, or out of scope?

> **Status:** designed during a command-tool outage; **not implemented.** Sequence after the in-flight
> accounting work. This is a *new module* (peer of Accounting/Stock/Selling/Buying), not a Phase-4
> accounting sub-module.
