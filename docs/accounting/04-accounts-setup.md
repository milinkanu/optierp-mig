# 04 · Accounts Setup

> Sub‑module of [ACCOUNTING_GAP_AND_PLAN.md](../ACCOUNTING_GAP_AND_PLAN.md). ERPNext workspace card: **Accounts Setup**.

## Status today — 🟡 backend ready, UI thin

The masters exist; the **setup UX** is the gap. Most of this sub‑module is engine descriptors +
frontend, not new posting logic.

- **Account / Chart of Accounts** — ✅ tree (`ltree`), full validation ([accounts_masters.py](../../backend/app/services/accounts_masters.py)). **No dedicated UI** (card `planned`).
- **Cost Center** — ✅ engine tree at `/m/cost-center`.
- **Fiscal Year** — ✅ backend; list‑only, not in sidebar.
- **Mode of Payment, Bank Account, Tax Category, Payment Terms Template, Terms Template** — ✅ masters.
- **Period Closing Voucher** — ✅ atomic close + freeze.

## Gaps vs ERPNext

| # | Gap | State | P | Note |
|---|---|---|---|---|
| 1 | **Chart of Accounts tree UI** | 🔴 (backend done) | 1 | Browse/expand, create under group, set account type, freeze/disable, balances inline. Highest‑use setup screen. |
| 2 | **Chart of Accounts Importer** | 🔴 | 2 | Import a standard CoA template (CSV) so a new company isn't built account‑by‑account. |
| 3 | **Accounting Dimensions** (generic, beyond Cost Center) | 🟡 cost center only | 3 | User‑defined GL dimensions (Project, Branch) injected into every voucher + report filter. |
| 4 | **Accounts Settings** (global config) | 🟡 scattered | 3 | Frozen‑date, default cost center, rounding, allow‑negative, credit‑limit enforcement — one settings screen. |
| 5 | **Party Account / Party Link** | 🟡 | 3 | Per‑party default receivable/payable + advance account; link a Customer↔Supplier as one entity. |
| 6 | **Accounting Period** (lock by doctype) | 🔴 | 4 | We freeze by date globally; per‑doctype period locks are extra ceremony. Defer. |
| 7 | **Cost Center Allocation** | 🔴 | 4 | Auto‑split a posting across cost centers by %. Niche. |
| 8 | **Finance Book, Exchange Rate Revaluation, Pegged/Exchange settings** | 🔴 | 5 | Master §3.2/§3.5 — **skip**. |
| 9 | **Repost / ledger‑health / bisect tools** | 🔴 | — | Master §3.3 — **skip** (invariants make them moot). |

## Simplifications

- **Single source of freeze**: keep `accounts_frozen_upto`; do **not** add per‑doctype Accounting
  Period locks unless audit demands it.
- **Dimensions = a thin generic framework**, not ERPNext's full injection engine. A dimension is an
  engine‑served master whose values become an optional FK column on GL rows + an optional report
  filter. Start with Cost Center (done) + Project; generalize only as needed.
- **Settings as one descriptor‑backed singleton**, not 100 fields.

## Build‑out

### Phase 0 — Chart of Accounts UI *(frontend; backend ready)*
- Tree view: expand groups, show balance per node, create child under a group, edit type/freeze/disable.
- Wire Fiscal Year, Mode of Payment, Bank Account into the Setup sidebar (engine masters).
- *Acceptance:* a user can build a CoA and see live balances without touching the API.

### Phase 1 — Onboarding
- **CoA Importer** (*bespoke import service*): parse a CSV of accounts (number, name, parent, type) → create the tree atomically. Ship 1–2 standard templates (e.g. India trading).
- *Acceptance:* importing a 60‑line template yields a valid, balanced (empty) CoA.

### Phase 2 — Dimensions & settings
- **Accounting Dimension** (*engine master + posting hook*): declare a dimension; its value becomes an optional dimension column on GL rows and a filter in reports. Wire one new dimension (Project) end‑to‑end as proof.
- **Accounts Settings** (*engine singleton*): surface frozen date, default cost center, rounding behavior, allow‑negative, credit‑limit toggle.
- **Party Account / Party Link** (*engine child + small service*): per‑party default accounts; merge a customer/supplier into one legal entity for combined statements.
- *Acceptance:* a Project dimension flows from invoice → GL → P&L‑by‑project filter.

## Engine vs bespoke
- **Engine:** Chart of Accounts (tree, exists), Cost Center, Fiscal Year, Mode of Payment, Bank
  Account, Tax Category, Accounting Dimension, Accounts Settings (singleton), Party Account.
- **Bespoke:** CoA Importer (atomic tree build), the dimension **posting hook** in `gl.py`, Period
  Closing (exists).
</content>
