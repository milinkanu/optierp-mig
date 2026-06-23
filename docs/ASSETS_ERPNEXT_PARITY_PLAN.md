# Assets — ERPNext Parity Gap Analysis & Plan

**Goal:** measure our Assets module against the *full* ERPNext v15 Assets module (per
https://docs.frappe.io/erpnext/assets and the `reference/erpnext/erpnext/assets` source),
and lay out what to build to reach the level you want.

**Source of truth:** ERPNext ships **~22 asset DocTypes**. This doc lists every one, says
whether we have it, and — for the gaps — gives a plain recommendation: **BUILD** (real value
for an appliance distributor), **SKIP** (enterprise ceremony that contradicts the MSME-lean
thesis), or **OPTIONAL** (build only if you actually need it).

> Reminder of the house rule for this project: *copy the value, drop the ceremony.* You also
> just had me **merge** Asset Maintenance + Asset Repair because two near-identical screens was
> redundant — full ERPNext parity would re-split them and add teams/SLAs. I flag those tensions
> below rather than blindly cloning.

---

## 1. Where we stand (Phases 1–3 + extras, all built & verified)

| Capability | Status |
|---|---|
| Asset Category (method, life, salvage, 3 GL accounts) | ✅ (simplified: accounts on the category, not a per-book child) |
| Location | ✅ (simplified: flat, no tree/geo) |
| Asset register: create / submit / cancel | ✅ |
| Depreciation: **Straight Line**, **Written Down Value**, **Manual** | ✅ |
| Depreciation schedule + idempotent daily posting job + manual "depreciate now" | ✅ |
| Disposal: **Sell** / **Scrap** → gain/loss Journal Entry, halts depreciation | ✅ |
| Asset Movement (location/custodian + history) | ✅ (simplified: one asset per move) |
| Asset Maintenance **& Repair** (one log master, "Repair" is a type) | ✅ (merged per your call) |
| Asset Value Adjustment (impairment **and** appreciation → Revaluation Surplus) | ✅ |
| Non-depreciable categories (Land / freehold, held at cost) | ✅ |
| `is_fixed_asset` Item → auto-create draft Asset from a Purchase Invoice line | ✅ |
| Opening accumulated depreciation (mid-life asset onboarding) | ✅ |

---

## 2. Full ERPNext DocType list vs us

| # | ERPNext DocType | Us | Verdict |
|---|---|---|---|
| 1 | Asset | ✅ | done |
| 2 | Asset Category | ✅ | done (simplified) |
| 3 | Asset Category Account (per-company/book accounts child) | ➖ | **SKIP** — single company/book; accounts sit on the category |
| 4 | Asset Depreciation Schedule (submittable, per finance book) | ◑ | we have the schedule as a child of Asset — enough for one book |
| 5 | Asset Finance Book (parallel schedules per book) | ❌ | **OPTIONAL** — dual-book (Companies Act vs IT Act) depreciation |
| 6 | Location | ✅ | done (simplified) |
| 7 | Asset Movement (+ Movement Item child) | ✅ | done (single-asset; no batch child) |
| 8 | Asset Maintenance + Task + Log + Team + Team Member | ◑ | merged to **one log**; scheduling = **BUILD**, teams/SLAs = **SKIP** |
| 9 | Asset Repair (+ Consumed Item child) | ◑ | merged into maintenance; stock-consumption + capitalisation = **OPTIONAL** |
| 10 | Asset Value Adjustment | ✅ | done |
| 11 | Asset Capitalization (+ stock/asset/service item children) | ❌ | **BUILD** — assemble an asset from parts + labour |
| 12 | Asset Shift Allocation + Shift Factor | ❌ | **SKIP** — factory shift depreciation, not for a distributor |
| 13 | Asset Activity (system event timeline) | ❌ | **SKIP** — our audit log already records every change |
| 14 | Linked Location | ❌ | **SKIP** — part of the location-tree machinery |

Plus these ERPNext *capabilities* (not separate DocTypes):

| Capability | Us | Verdict |
|---|---|---|
| **CWIP** (Capital Work in Progress — cost accrues until ready-for-use, then capitalise) | ❌ | **BUILD** (pairs with Capitalization) |
| Depreciation method **Double Declining Balance** | ❌ | **OPTIONAL** — niche method |
| **Daily pro-rata** first/last period (asset bought mid-month) | ❌ | **BUILD** — real accuracy gap |
| Explicit **Rate of Depreciation %** input for WDV (vs derived from salvage) | ❌ | **BUILD** — small, India WDV blocks use fixed rates |
| Disposal via **Sales Invoice** (tax invoice + GST on used-asset sale) | ◑ | **BUILD** — we only post a plain JE today |
| **Cancel / restore** posted depreciation (reverse the JEs) | ❌ | **BUILD** — small but expected |
| **Reports**: Fixed Asset Register / Net Block, Depreciation Ledger, Asset-wise depreciation | ❌ | **BUILD** — this is the originally-planned Phase 4 |
| Multiple assets from one purchase line (qty > 1) | ➖ | **SKIP** — one Asset per line (offer split later if asked) |

---

## 3. Recommended plan (high value first)

### Phase 4 — Reports *(do first; already the planned next step)*
- **Fixed Asset Register / Net Block** — per asset/category: gross, accumulated depreciation,
  book value, as of any date.
- **Asset Depreciation Ledger** — every posted depreciation entry (date, amount, JE link).
- **Asset-wise depreciation** — the schedule across assets, projected vs posted.
- Read-only endpoints + a Reports surface in the Assets workspace.

### Phase 5 — Acquisition completeness
- **CWIP accounting** — a category flag (`enable_cwip`) so a fixed-asset purchase debits a
  *Capital Work in Progress* account; the asset is **capitalised** (moved CWIP → Fixed Asset)
  when it's ready for use and depreciation starts then.
- **Asset Capitalization** — build a new asset by combining **stock items consumed + service/
  labour costs (+ optionally scrapped assets)** into one capitalised value. (Lean: a bespoke
  `POST /assets/capitalize` that posts the assembling JE and creates the asset.)
- **Disposal via Sales Invoice** — option to sell an asset on a real tax invoice (GST), with
  the gain/loss still booked vs book value, instead of a plain JE.

### Phase 6 — Depreciation accuracy — ✅ DONE (migration 0056)
- ✅ **Daily pro-rata** (`daily_prorata` on the category) — Straight-Line periods are weighted by
  their actual day count (Feb < Jan) instead of an equal split; total still equals the base.
- ✅ **Explicit WDV rate %** (`rate_of_depreciation` on the category) — used directly (e.g. IT-Act
  15%/40% blocks) instead of deriving from salvage; works with 0% salvage too.
- ✅ **Cancel/restore depreciation** (`POST /assets/{id}/cancel-depreciation`) — writes reversing GL
  entries for every posted depreciation JE, clears the rows' posted flags, reopens the asset
  (status → Submitted) so the schedule can be re-posted. Ledger stays append-only.
- ⏸️ **Double Declining Balance** — left out (niche; WDV with an explicit rate covers most needs).
- *Tests:* +3 unit (explicit rate, pro-rata day-weighting, rate>0) + 2 integration (cancel+re-post,
  WDV explicit-rate category). Verified live (forklift depreciation cancelled → status Submitted,
  accumulated ₹0, rows reopened).

### Phase 7 — Maintenance scheduling *(keep it ONE doctype)*
- Upgrade the maintenance log to **recurring scheduled tasks**: periodicity (monthly/quarterly/
  yearly), `next_due_date`, an **Overdue** view, mark-complete → roll the next due date forward.
- **Keep** the single merged Maintenance & Repair master (no teams, members, or SLAs).

### Deliberately SKIPPED (enterprise ceremony — revisit only on a real need)
- **Multiple Finance Books** + Asset Category Account child (dual-book parallel depreciation).
- **Shift-based depreciation** (Shift Allocation / Shift Factor).
- **Maintenance Teams / Members / SLA tasks**, **Asset Activity** timeline, **Location tree +
  geolocation**, **multi-asset Movement batches**.

---

## 4. Optional (only if you say so)
- **Multiple Finance Books** — if you need Companies-Act *and* Income-Tax-Act depreciation
  computed inside the ERP (most MSMEs let their CA do the IT-Act block separately). This is the
  single biggest structural change (asset gets N schedules instead of one) — worth a dedicated
  decision.
- **Asset Repair with consumed stock + capitalisation** — if repairs routinely consume tracked
  inventory and you want the repair to add to the asset's value.

---

## 5. Suggested sequencing
1. **Phase 4 (Reports)** — fast, high value, finishes the original plan.
2. **Phase 6 (pro-rata + WDV rate + cancel depreciation)** — correctness, mostly backend.
3. **Phase 5 (CWIP + Capitalization + SI disposal)** — the biggest functional additions.
4. **Phase 7 (maintenance scheduling)** — quality-of-life.
5. Finance Books / shift depreciation only if a real requirement appears.

Each phase ships the same way as 1–3: migration + service + engine/bespoke + frontend +
unit/integration tests + Playwright verification + a commit, with manual verification steps.
