# Accounting Module — Gap Analysis & Phased Implementation Plan

**Scope:** OptiReach ERP Accounting module vs ERPNext v15 Accounts, with simplification
recommendations where ERPNext is over‑engineered for a real SMB user.
**Verified against code on:** 2026‑06‑19 (models/services/schemas/API/frontend read directly).
**Business context assumed:** appliance trading/distribution — single company, single base
currency, India‑style GST/TDS likely relevant, no stock‑exchange listing (Share Management is
"cap‑table for a private company", not a trading desk).

> This is the **master plan**. Each of the nine ERPNext Accounting sub‑modules has its own
> focused build‑out spec under [docs/accounting/](accounting/). This file is the index, the
> overall gap picture, and the phase ordering across sub‑modules.

---

## 0. Plain‑language summary (read this first)

Think of Accounting as a **bank for the whole business**:

- The **Chart of Accounts** is the list of "buckets" money can sit in (cash, what customers owe
  us, what we owe suppliers, sales income, rent expense…).
- The **General Ledger (GL)** is the master statement — an append‑only list of every rupee that
  moved, always balanced (every debit has an equal credit).
- **Invoices, Payments, Journal Entries** are the documents that push entries into the ledger.
- **Reports** (Balance Sheet, P&L, Trial Balance) are just different ways of reading the ledger.

**Where we stand:** the *engine and the everyday workflow are genuinely done.* We have an
immutable, self‑balancing GL with frozen‑period protection; sales/purchase invoices that post
correctly and reverse cleanly; payments with allocation and reconciliation; manual journals;
budgets that actually block over‑spend; period closing; and seven financial reports. A real
business could keep its books today. This is **not** a greenfield build — it is a build‑*out*.

**What's actually missing** falls into three buckets:

1. **Polish on what exists** — a few stubs (inclusive taxes, a couple of placeholder UI cards),
   reports ERPNext has that we don't, opening‑balance tooling.
2. **Advanced sub‑module depth** — TDS/withholding, tax rules, bank‑statement import &
   matching, advance payments as first‑class, dunning, statements of account.
3. **Four net‑new areas with zero code today** — **Banking tooling**, **Subscription**,
   **Share Management**, and most of **POS** (deferred; see §3).

**Where ERPNext is over‑built:** the `accounts` app has **167 doctypes** and **57 reports**. A
huge fraction (ledger‑health monitors, bisect tools, repost queues, finance books, pegged
currencies, multiple POS child tables, regional VAT lines) is ceremony that confuses SMB users
or solves problems we don't have at our scale. This plan **deliberately copies the value and
drops the ceremony**, and calls out each cut so it's a decision, not an accident.

---

## 1. What the module does today (verified inventory)

### 1.1 Masters & configuration
| Master | Status | Notes |
|---|---|---|
| **Account (Chart of Accounts)** | ✅ tree (Postgres `ltree`) ([accounts_masters.py](../backend/app/services/accounts_masters.py)) | `root_type`, `report_type`, `account_type`, `is_group`, currency, freeze/disable. Create + tree nav. Debit/credit rule validation. **No dedicated UI view yet** (card is `planned`). |
| **Cost Center** | ✅ tree (`ltree`), engine descriptor | full CRUD via `/m/cost-center`. Optional on every GL row. |
| **Fiscal Year** | ✅ | start/end, `is_closed`; enforced on GL posting. List only. |
| **Tax Category** | ✅ engine master | groups parties → auto‑selects tax template. |
| **Tax Template (Sales/Purchase)** | ✅ bespoke ([accounts_masters.py](../backend/app/services/accounts_masters.py)) | 5 charge types, Add/Deduct, Valuation/Total categories, per‑company default. **No dedicated UI** (managed inline on invoices; card `planned`). |
| **Payment Terms Template** | ✅ engine master | installment schedule (credit days, portion). |
| **Mode of Payment** | ✅ | default account per mode. |
| **Bank Account** | ✅ | links a GL account; IBAN, is_default. |

### 1.2 General Ledger engine — the foundation
- **GL Entry** is **immutable** (DB trigger blocks UPDATE/DELETE), **append‑only on cancel**
  (writes mirror entries with `is_cancellation=true`, never edits history), and validated by a
  **deferred DB constraint** (`SUM(debit)=SUM(credit)` per voucher at commit — not just in app
  code). ([gl.py](../backend/app/services/gl.py))
- **Frozen periods**: `accounts_frozen_upto` blocks back‑dated posting; set by Period Closing.
- **Budget validation**: per expense row, Stop/Warn/Ignore.
- **Multi‑currency**: stores base + account‑currency amounts, per‑row exchange rate.
- This engine is the single biggest asset in the module. **Do not regress it** (see §5).

### 1.3 Transactions (hand‑coded services)
| Doc | Status | GL effect on submit | Notes |
|---|---|---|---|
| **Journal Entry** | ✅ | posts balanced rows | draft→submit→cancel, party required on AR/AP, multi‑currency, clearance date. |
| **Sales Invoice** | ✅ | Dr Receivable / Cr Income + taxes + rounding | cycle links (SO/DN), returns/credit notes, PDF, derived status, outstanding tracking. |
| **Purchase Invoice** | ✅ | Cr Payable / Dr Expense + taxes | cycle links (PO/PR), perpetual‑inventory `stock_received_but_not_billed`, debit notes, PDF. |
| **Payment Entry** | ✅ | party rows + bank/cash rows | Receive/Pay/Internal Transfer, allocations, deductions, clearance date. |
| **Payment Reconciliation** | ✅ (tool) | none (allocations only) | fetch unreconciled, apply allocations, adjust outstanding. |
| **Budget** | ✅ | none (control doc) | annual per FY/cost center; enforced on GL. |
| **Period Closing Voucher** | ✅ | zeroes P&L → retained earnings | atomic create+submit, freezes prior periods. |

### 1.4 Reports
GL, Trial Balance, Balance Sheet, P&L, AR aging, AP aging, Cash Flow, Bank Reconciliation
(read‑only) — all live in [financial_reports.py](../backend/app/services/financial_reports.py)
and surfaced as tabs in [ReportsView.vue](../frontend/src/views/accounts/ReportsView.vue).

### 1.5 Frontend
Invoice list/form (sales & purchase), Journal Entry, Payment Entry, Payment Reconciliation,
Budget, and the 7‑tab Reports view all exist and work. **Three placeholder cards** point
nowhere: **Bank Reconciliation** (the report tab exists — just unwired), **Chart of Accounts**
(no dedicated tree view), **Tax Template** (no dedicated editor).

---

## 2. Gap analysis vs ERPNext v15 Accounts

Legend: 🔴 missing · 🟡 partial · 🟢 present · **P = priority** (1 highest)
Sub‑module column maps to the nine ERPNext workspace cards in the screenshot.

### 2.1 Highest‑leverage gaps (cross‑cutting)
| # | Gap | Sub‑module | State | P | Why it matters |
|---|---|---|---|---|---|
| 1 | **Chart of Accounts UI** (tree browse/edit + COA importer) | Setup | 🟡 backend done, no view | **1** | The single most‑used setup screen. Backend is ready; this is mostly frontend. |
| 2 | **Opening balances** (Opening Invoice Creation Tool + opening GL) | Setup / Invoicing | 🔴 | **1** | No clean way to go live with existing receivables/payables/account balances. Foundational for onboarding. |
| 3 | **Advance payments as first‑class** | Payments | 🟡 field only | **1** | `advance_paid` exists but no advance receipt flow / tax‑on‑advance. Common in trading (deposits). |
| 4 | **Tax Withholding (TDS/TCS)** | Taxes | 🔴 | **2** | India trading needs TDS on supplier payments. Legal requirement, not optional. |
| 5 | **Bank statement import + reconciliation tool** | Banking | ✅ DONE (2026‑06‑20) | **2** | Import statement lines + match to uncleared vouchers (sets clearance_date). Create-from-unmatched + split allocations deferred to a sub-slice. |
| 6 | **Inclusive taxes** | Taxes / Invoicing | 🔴 blocked | **2** | `included_in_print_rate` raises `ValidationError`. MRP‑inclusive pricing is normal in retail/appliances. |
| 7 | **Missing standard reports** | Financial Reports | 🟡 | **2** | No Sales/Purchase Register, Gross Profit, Customer/Supplier Ledger Summary, Budget Variance, item‑wise registers. |

### 2.2 Sub‑module depth gaps
| Gap | Sub‑module | State | P | Stance |
|---|---|---|---|---|
| Tax Rule (auto‑pick template by territory/party) | Taxes | 🔴 | 3 | Build lean — see [05-taxes.md](accounting/05-taxes.md). |
| Item Tax Template (per‑item rate override) | Taxes | 🔴 | 3 | Needed for mixed‑GST‑slab catalogs. |
| Payment Request / Payment Order | Payments | 🔴 | 3 | Payment Request useful (email + gateway link); Payment Order is bank‑file batching — defer. |
| Dunning (overdue reminders) | Payments | 🔴 | 3 | Reminder letters with interest; medium value. |
| Process Statement of Accounts (email AR statements) | Payments | 🔴 | 3 | Bulk customer statements; medium value. |
| Accounting Dimensions (beyond Cost Center) | Setup | 🟡 cost center only | 3 | Generic dimension framework — see [04-accounts-setup.md](accounting/04-accounts-setup.md). |
| Accounting Period (lock by doctype) | Setup | 🟡 FY‑only | 4 | We freeze by date; per‑doctype period lock is extra. Defer. |
| Monthly Distribution (budget seasonality) | Budget | 🔴 | 4 | Spreads annual budget across months. Low value for SMB. |
| Exchange Rate Revaluation | Setup | 🔴 | 4 | Only matters with material forex balances. Defer until multi‑currency is real. |
| Cost Center Allocation | Setup | 🔴 | 4 | Auto‑split postings across cost centers. Niche. |
| Subscription (recurring billing) | Subscription | 🔴 | 3 | Net‑new — see [09-subscription.md](accounting/09-subscription.md). Build if recurring contracts exist. |
| Share Management (cap table) | Share Mgmt | 🔴 | 4 | Net‑new — see [08-share-management.md](accounting/08-share-management.md). Lowest priority. |
| Invoice Discounting | Banking | 🔴 | 5 | Bill discounting finance. Skip unless asked. |
| Loyalty Program | (no card) | 🔴 | 5 | Retail loyalty. Skip for trading/distribution. |
| POS (Profile, Opening/Closing, consolidation) | Invoicing | 🔴 | 4 | Big subsystem — defer unless a retail counter is in scope. See [01-invoicing.md](accounting/01-invoicing.md). |

### 2.3 Engine/correctness gaps (small but real)
| Gap | State | Note |
|---|---|---|
| Inclusive taxes | 🔴 blocked | [taxes_and_totals.py](../backend/app/services/taxes_and_totals.py) raises on `included_in_print_rate`. |
| Finance Book (parallel ledgers) | 🔴 | ERPNext over‑build for us — **skip** (see §3). |
| Payment Ledger (separate from GL) | 🔴 | ERPNext keeps a second ledger for AR/AP; we read outstanding off invoices — simpler, **keep our model** (see §3). |
| Repost / ledger‑health / bisect tools | 🔴 | Diagnostic ceremony — **skip** (see §3). |

---

## 3. Where ERPNext is over‑engineered → how we simplify

The user POV test: *can the owner of a 20‑person appliance distributor run their books without
hiring a Frappe consultant?* Each item below is a deliberate "copy the value, drop the ceremony"
decision.

### 3.1 Payment Ledger as a second ledger → keep outstanding on the invoice
ERPNext maintains a whole **Payment Ledger Entry** doctype parallel to the GL purely to compute
party outstanding, plus repost tools to rebuild it when it drifts.
**Simplify:** we already track `outstanding_amount` directly on the invoice and adjust it on
payment submit/cancel. AR/AP aging reads the invoice, not a second ledger. One source of truth,
no repost queue. Keep it.

### 3.2 Finance Books / multiple accounting bases → single base
ERPNext supports parallel books (e.g. separate IFRS/tax depreciation ledgers).
**Simplify:** single company, single base currency, one set of books. Drop Finance Book entirely.
Revisit only if statutory dual‑GAAP reporting is ever required.

### 3.3 Ledger‑health monitor, bisect, repost queues → trust the invariants
ERPNext ships `ledger_health`, `bisect_accounting_statements`, `repost_accounting_ledger`,
`repost_payment_ledger` to detect and repair an unbalanced ledger.
**Simplify:** our GL **cannot** go unbalanced — a deferred DB constraint enforces it at commit and
a trigger blocks edits. We don't need tools to repair drift that can't happen. Skip all of them.

### 3.4 POS as ~15 doctypes → one optional counter screen (deferred)
ERPNext POS = POS Profile, Settings, Opening/Closing Entry (+5 child tables), Merge Log, Cashier
Closing, payment‑method tables.
**Simplify:** unless a physical retail counter is in scope, **defer POS entirely**. If needed, a
Sales Invoice with `is_pos` + a multi‑mode payment child table covers 90% — see
[01-invoicing.md](accounting/01-invoicing.md). Don't port the closing/merge machinery.

### 3.5 Pegged currencies, regional VAT lines, currency‑exchange API config → manual rate
ERPNext has `pegged_currencies`, `currency_exchange_settings` (live FX API), `south_africa_vat_account`.
**Simplify:** manual conversion rate per document (already how it works). No live‑FX fetch, no
regional VAT line mapping. Add a single currency‑exchange rate master only if needed.

### 3.6 Deferred revenue/expense engine → skip until subscriptions exist
ERPNext recognizes deferred revenue over time via `process_deferred_accounting`.
**Simplify:** defer (pun intended). Only relevant alongside Subscription; revisit there.

> Everything in §3 is **explicitly out of scope** unless a future requirement reverses it. The
> per‑sub‑module docs do not re‑litigate these.

---

## 4. Phased implementation plan

Phases are ordered by leverage (what unblocks the most real‑world use), not by sub‑module. Each
phase lists which sub‑module doc carries the detail. **House rule throughout:** masters/config are
**engine‑served** (a `DocTypeDescriptor` recipe card → free list/form/permissions); anything that
**posts to the GL or runs accounting rules stays a hand‑written service** behind the engine's
form/list boundary (see §6 and [ENGINE_GUIDE.md](ENGINE_GUIDE.md)).

### Phase 0 — Wire up what's already built ✅ DONE (2026‑06‑19)
Pure frontend / plumbing; backend already supported all of it.
- ✅ **Chart of Accounts tree view** — browse/expand + create‑under‑group, with group badges and
  root types ([ChartOfAccountsView.vue](../frontend/src/views/accounts/ChartOfAccountsView.vue)).
  *Freeze/disable/rename still needs a backend update endpoint — see Phase 0.5 below.*
- ✅ **Tax Template editor** — Sales/Purchase list + expand‑to‑view + create
  ([TaxTemplateView.vue](../frontend/src/views/accounts/TaxTemplateView.vue)). *Update/delete needs
  a backend endpoint — Phase 0.5.*
- ✅ **Bank Reconciliation card** — now points at the existing `/reports?tab=bank-recon`.
- Verified: `vue-tsc` + `vite build` clean; both screens render against demo data (82 accounts,
  3 GST templates) via the Playwright harness.

### Phase 0.5 — Small backend follow‑ups ✅ DONE (2026‑06‑19)
- ✅ **Account update** (`PATCH /accounts/{id}`): rename (cascades the ltree path to descendants),
  account number/type/currency, freeze/disable. Structural fields (root_type/parent/is_group) not editable.
- ✅ **Tax Template update/delete** (`PATCH`/`DELETE /tax-templates/{id}`): full header+rows replace;
  hard delete (safe — posted documents copy their tax rows, no stored FK to the template).
- ✅ **Fiscal Year, Mode of Payment, Bank, Bank Account** registered as engine masters (`/m/<slug>`),
  permissions auto‑seeded from the descriptors; surfaced in the accounting sidebar.
- Verified: 88 unit tests + descriptor‑drift green, ruff clean, vue‑tsc clean; live CRUD exercised
  via Playwright (account freeze toggle; tax‑template create→delete; fiscal‑year master renders).

### Phase 1 — Onboarding & the everyday gaps *(the gating set for real use)*
- ✅ **Inclusive taxes** DONE (2026‑06‑19) — `taxes_and_totals` now back‑calculates the net rate
  when `included_in_print_rate` is set (ERPNext `determine_exclusive_rate` + rounding
  reconciliation). Flag added to the shared `TaxRowMixin` (migration 0038, all six tax tables),
  plumbed through Sales/Purchase Invoice, and exposed as a template‑level "tax‑inclusive (MRP)"
  toggle. 5 new engine unit tests (118 MRP → net 100/tax 18; CGST+SGST; multi‑item; exclusive
  regression; Actual‑inclusive rejected). Live‑verified via Playwright. ([05](accounting/05-taxes.md))
- ✅ **Core reports** DONE (2026‑06‑19): Sales Register, Purchase Register, Customer Ledger Summary,
  Supplier Ledger Summary, **and Gross Profit** — read‑only endpoints in `financial_reports.py` + tabs
  in `ReportsView.vue`; verified live. Gross Profit takes COGS from each item's latest moving‑average
  stock valuation (items sold without a recorded stock cost show 0 / 100% margin — flagged in the UI).
  ([03](accounting/03-financial-reports.md))
- ✅ **Opening Invoice Creation Tool** DONE (2026‑06‑19): `is_opening` on invoices (migration 0039),
  bulk tool (`opening_invoice.py` → `POST /opening-invoices`) that posts each outstanding against the
  company's Temporary Opening account (no income/expense, no tax), shows in AR/AP aging, and is
  excluded from the registers. Frontend tool under Setup. Integration‑tested + live‑verified.
  *Opening account balances (cash/bank/capital) use a normal Journal Entry against Temporary Opening
  — no new code needed.* ([01](accounting/01-invoicing.md), [04](accounting/04-accounts-setup.md))
- ✅ **Advance payments first‑class** DONE (2026‑06‑19): an on‑account receipt already sits as a
  credit on the party's receivable/payable (ERPNext's party‑account advance model), so "first‑class"
  is the loop‑closing UX — the invoice detail now shows the party's **available advances** and
  applies them in one click (reuses the Payment Reconciliation service: link + drop outstanding, no
  new GL). Verified live (₹5k advance → invoice outstanding ₹71,594 → ₹66,594). *Deliberately skipped:
  a dedicated advance account + reclassification (party‑account model is simpler & correct).*
  *GST‑on‑advance: N/A for goods (Notif. 66/2017 withdrew it) — would add only if services are sold.*
- Acceptance: a new company can be onboarded with opening balances; integration tests for each.

### Phase 2 — Compliance & banking *(legal + daily ops)* — IN PROGRESS
- ✅ **Budget Variance report** DONE (2026‑06‑19): per budgeted account, budget vs actual (GL net) for
  a fiscal year + variance/%; `financial_reports.budget_variance` → `/reports/budget-variance` → a
  Budget Variance tab. Verified live (Marketing 94% / Rent 85% / Salary 92% under budget). ([07](accounting/07-budget.md))
- ✅ **Budget Monthly Distribution** DONE (2026‑06‑19): optional seasonality on budgets — a month‑to‑date
  cap (annual × cumulative monthly %) enforced in `gl.py` alongside the annual cap; migration 0040;
  budget form picker. ([07](accounting/07-budget.md))
- ✅ **TDS (Tax Withholding) on Purchase Invoice** DONE (2026‑06‑19): `TaxWithholdingCategory` engine
  master (rate + payable account); the PI withholds rate%×net (migration 0041), reduces the supplier
  payable, credits TDS Payable; outstanding nets the TDS. Frontend picker + integration test.
  ([05](accounting/05-taxes.md))
- ✅ **Item Tax Template** DONE (2026‑06‑19): per‑item GST override — `taxes_and_totals` honours a
  per‑item rate by tax‑account head; `ItemTaxTemplate` engine master (parent+child) + `Item` link
  (migration 0042); both invoice services + Item form wired. Unit + integration tests.
  ([05](accounting/05-taxes.md))
- ✅ **Bank statement import + reconciliation tool** DONE (2026‑06‑20): `BankTransaction` model
  (migration 0043) for imported statement lines; bespoke service + endpoints under `/bank-transactions`
  (import, list, match-suggestions, reconcile, unreconcile, delete, summary); a statement line matches
  one uncleared Payment Entry / Journal Entry and sets that voucher's `clearance_date` (the existing
  bank-rec mechanism), so `balance_per_bank` converges. Frontend tool at `/bank-reconciliation`
  (CSV/manual import, suggestions, match/unmatch, summary cards). Seed: `BankAccount` masters + demo
  statement lines. Integration-tested.
  - ✅ **Create-from-unmatched-line** DONE (2026‑06‑20): an unmatched line (bank charges, interest)
    creates a balanced Journal Entry against a chosen contra account (deposit ⇒ Dr bank/Cr contra;
    withdrawal ⇒ Dr contra/Cr bank), auto-submitted + cleared + matched. `created_voucher` flag
    (migration 0044) makes unmatch *cancel* that JE (GL reverses) rather than just un-clear it.
    `POST /bank-transactions/{id}/create-voucher`; frontend "record as a journal entry" form in the
    match panel. Integration-tested.
  - ✅ **Cancel-releases-line integrity** DONE (2026‑06‑22): cancelling a Payment Entry / Journal Entry
    from its own screen now reverts any bank line matched to it back to Unreconciled (no stale
    "Reconciled" pointing at a cancelled doc). `bank_reconciliation_tool.release_matched_transactions`
    called from both cancel paths (lazy import). Integration-tested.
  - ✅ **Reconcile against an open invoice** DONE (2026‑06‑22): a bank line can settle an open
    Sales (deposit) / Purchase (withdrawal) invoice directly — `GET /bank-transactions/{id}/invoice-suggestions`
    (outstanding>0, nearest-amount first) + `POST /bank-transactions/{id}/pay-invoice`, which auto-creates +
    submits a Payment Entry (Receive/Pay) allocated to the invoice, clears it, and matches the line (the
    invoice's outstanding drops). created_voucher ⇒ unmatch cancels the PE and restores the invoice. Frontend
    "Open invoices to settle" panel with **clickable invoice links** to the invoice detail page. More useful
    than ERPNext, which only direct-matches POS/`is_paid` invoices. Integration-tested.
  - Also renamed for clarity (2026‑06‑22): the **tool** stays "Bank Reconciliation"; the **report** is now
    "Uncleared Items" (was "Bank Rec Statement"), with a caption explaining the books↔bank relationship.
  - ✅ **Voucher detail pages + full audit trail** DONE (2026‑06‑22): read-only `/payment-entries/:id`
    (money flow + **allocated invoices as clickable links** — the "retract to invoices" trace) and
    `/journal-entries/:id` (balanced Dr/Cr lines). Matched vouchers + voucher suggestions in the bank-rec
    tool AND the PE/JE list rows now link to them. Chain: bank line → Payment Entry → invoice → invoice page.
  - ✅ **Opening bank balance** (2026‑06‑22): Dr HDFC / Cr Shareholders Funds 10,00,000, cleared at go-live
    (seed_demo.py + applied live) so the demo bank reads positive — HDFC books now +4,66,952 (was −5,33,048).
  - **Still deferred:** N:1 split allocations; statement opening/closing-balance capture.
    ([06](accounting/06-banking.md))
- ✅ **TCS on Sales Invoice** DONE (2026‑06‑22): pick a TCS `TaxWithholdingCategory` on a Sales Invoice →
  it collects `rate% × base_net_total` ON TOP of the bill (the customer owes more), credits **TCS Payable**,
  and sets outstanding = grand + TCS. Mirror of TDS with the sign flipped (sales_invoice.py create +
  _build_gl_rows + submit). Frontend: the withholding picker now shows for sales too (filtered to kind=TCS),
  with a "TCS collected (+)" detail line; PDF gets a "TCS collected" line. **Also fixed a latent bug**: the
  invoice cancel guard compared outstanding to grand to detect a payment, which falsely blocked cancelling
  ANY TDS/TCS invoice — now compares to the withholding-adjusted outstanding (sales +TCS, purchase −TDS).
  seed_demo seeds TDS+TCS categories (+ TDS/TCS Payable accounts). Integration-tested (create → GL → cancel,
  both sides). ([05](accounting/05-taxes.md))
- ✅ **Standard tax library + auto-GST** DONE (2026‑06‑22): seeded the full set (Item Tax Templates GST
  0/5/12/18/28 each with CGST+SGST+IGST+Input rows; TDS 194C/H/I/J/Q; TCS 206C variants), removed a duplicate
  In-State template, and assigned every item a GST slab — so the **rate axis is automatic per item**. Then
  made the **place-of-supply axis automatic from the GSTIN**: `TaxCategory.is_inter_state` (migration 0045) +
  `resolve_tax_template(..., party_gstin=)` derives intra (CGST+SGST) vs inter (IGST) by comparing the first
  2 digits (state code) of the party's GSTIN (`tax_id`) to the company's — overriding the manual Tax Category,
  falling back to it (then company default) when there's no GSTIN/template. Wired into all 4 party tax
  resolutions (sales/purchase invoice + order). Customer/Supplier "Tax ID"→"GSTIN" (engine /meta, no rebuild).
  TDS/TCS stay manual by design. Net: enter a customer's GSTIN + items' GST slabs → invoices self-tax
  (intra/inter + per-item rate). Integration-tested + adversarially reviewed (28-agent workflow → 4 fixes):
  resolve_tax_template made deterministic + only overrides a *contradicting* manual category + ignores
  non-GSTIN tax_ids + skips disabled categories; **Sales/Purchase Orders now apply per-item GST + inclusive
  tax** (were dropping item_tax_rate/account_head_id/included_in_print_rate); the **purchase template is now
  `is_default`** so purchase Input GST auto-applies; Quotation also derives from GSTIN. Deferred: B2C
  no-GSTIN auto-GST, exports/SEZ/reverse-charge, and purchase intra/inter split (single Input GST template).
  ([05](accounting/05-taxes.md))
- ⏳ **Accounting Dimensions** + **Tax Rule** — DEFERRED as over‑built for our scale: Accounting
  Dimensions needs a GL‑schema column threaded through every posting path (Cost Center already covers
  the 80% case); Tax Rule (auto‑select template by territory) is a convenience over the existing
  tax‑category resolution. ([04](accounting/04-accounts-setup.md), [05](accounting/05-taxes.md))
- Acceptance met: TDS deducts correctly (integration‑tested); a mixed‑GST invoice taxes each item at
  its own rate (integration‑tested); monthly budget cap trips mid‑year.

### Phase 3 — Collections & receivables tooling — IN PROGRESS
First, two shared foundations (everything below stands on them):
- ✅ **Document delivery foundation** DONE (2026‑06‑22): **email infra** (attachments + an `email_logs`
  send-audit table + `email_id` on Customer/Supplier + Mailhog dev catcher; migration 0046) and **PDF for
  ALL transactional doctypes** (Quotation, Sales Order, Delivery Note, Purchase Order, Purchase Receipt,
  RFQ, Material Request, Stock Entry — 8 new print templates) with a **"Send by email" button** (PDF
  attached, recipient defaults to the party's saved email) on every document detail view. Generic endpoint
  `POST /print/{doctype}/{id}/email`. ([05](accounting/05-taxes.md), [06](accounting/06-banking.md))
- ✅ **Process Statement of Accounts** DONE (2026‑06‑22): per-customer ledger statement (opening + each
  voucher with running balance + closing + aging; cancelled vouchers excluded) → themed PDF → email,
  single or **bulk** ("email every customer with a balance"). `services/statements.py`, endpoints under
  `/reports/statement-of-accounts/...`, standalone `StatementOfAccountsView`. ([03](accounting/03-financial-reports.md))
- ✅ **Dunning** DONE (2026‑06‑22): overdue reminders with **escalation tiers** (`DunningType` master,
  migration 0047) + **per-invoice interest** (rate% p.a. × days overdue) + a flat fee; auto-picks the tier
  the customer has aged into; PDF + email, single or **bulk** ("email all overdue customers").
  `services/dunning.py`, endpoints under `/reports/dunning/...`, `DunningView`. ([02](accounting/02-payments.md))
- ✅ **AR/AP Summary + Collection (DSO) reports** DONE (2026‑06‑22): per‑customer/supplier outstanding
  rolled up across open invoices with aging buckets (`accounts_receivable_summary`/`accounts_payable_summary`),
  and a per‑customer **average days‑to‑pay** report (`collection_summary` — invoice date → final payment
  date, for invoices paid in the window). 3 endpoints under `/reports` + 3 ReportsView tabs (AR Summary,
  AP Summary, Collection Period). ([03](accounting/03-financial-reports.md))
- ✅ **Payment Request** DONE (2026‑06‑22, **lean / link‑less**): a `PaymentRequest` doc (migration 0048,
  bespoke service + router) — ask a customer to pay an amount (optionally vs a Sales Invoice), email it as a
  PDF (reuses the generic `/print/{doctype}/{id}/email`), track status (Requested→Paid→Cancelled).
  `payment_url` is the seam for a future online‑payment gateway. `PaymentRequestView` at `/payment-requests`.
  ([02](accounting/02-payments.md))
- ⏳ **Online payment‑gateway link** (UPI/Razorpay/Stripe "Pay Now" + webhook) and **scheduled auto‑send**
  of statements — DEFERRED (gateway needs creds + an integration; scope separately). ([02](accounting/02-payments.md))
- Verified: 108 unit + 64 integration tests (+ a targeted AR-summary/collection test), ruff + vue-tsc clean,
  migration 0048 applied, live Mailhog e2e + Playwright UI smoke (Payment Requests view + AR Summary tab),
  adversarial multi-lens review (on the email/PDF/statements/dunning core).

### Phase 4 — Net‑new sub‑modules *(build on demand)*
- **Subscription** (recurring invoicing). ([09](accounting/09-subscription.md))
- **Share Management** (private cap table). ([08](accounting/08-share-management.md))
- **POS** (only if a retail counter is in scope). ([01](accounting/01-invoicing.md))
- Acceptance: each is independently shippable; none blocks the others.

---

## 5. Correctness notes carried from current code (don't regress these)

- **GL is immutable & append‑only.** Never add an UPDATE/DELETE path to `gl_entries`. Cancellation
  = mirror entries with `is_cancellation=true`. New features post *new* entries; they never edit.
- **Deferred balance constraint** validates per‑voucher at commit. Any new posting service must
  emit balanced sets within one transaction.
- **Frozen periods** (`accounts_frozen_upto`) must be honored by every new posting path.
- **Outstanding lives on the invoice**, adjusted on payment submit/cancel — keep it the single
  source for AR/AP. Don't introduce a second ledger that can drift (see §3.1).
- **Status is derived**, not stored as a separate field beyond `docstatus`. New states must extend
  the derivation in [accounts_common.py](../backend/app/services/accounts_common.py).
- **Tax engine is a faithful ERPNext port** (5 charge types, per‑item chaining, Add/Deduct,
  Valuation/Total). Extend it (inclusive taxes) without breaking the existing chaining math.

---

## 6. Architecture: hand‑coded vs. engine‑served

**Engine‑served (recipe card only — `registry/descriptors.py`):** Chart of Accounts (tree),
Cost Center (tree), Fiscal Year, Mode of Payment, Bank, Bank Account, Tax Category, Payment Terms
Template, Terms Template, Accounting Dimension, Monthly Distribution, Subscription Plan, Share
Type, Shareholder, Dunning Type. These are reference/config data — declare them and get
list/form/permissions/sidebar for free.

**Bespoke services (form/list/permissions from the engine, but calculations hand‑coded):** every
document that posts to the GL or runs accounting rules — Journal Entry, Sales/Purchase Invoice,
Payment Entry, Payment Reconciliation, Budget, Period Closing, **and the new ones**: advance
payment allocation, TDS deduction, bank reconciliation matching, subscription invoice generation,
share transfer. The recipe card renders the screen; the posting logic lives in
`services/<name>.py` and the router in `api/v1/accounts/<name>.py`.

**Decision rule for every new accounting feature:**
> Does saving it change a ledger balance or run an accounting rule? → **bespoke service.**
> Is it pure reference/config data? → **engine descriptor.**
> Is it a report? → a read‑only endpoint in `financial_reports.py` (never engine‑served).

---

## 7. Scope decisions (answered 2026‑06‑19)

Product north star: **best‑in‑class accounting for Indian MSMEs, delivered as SaaS.** The answers
below are now binding for sequencing.

1. **Tax regime → full Indian GST + TDS + TCS.** Taxes is **promoted to a first‑class, high‑priority
   phase**, not a "later" nicety. CGST/SGST/IGST, inclusive pricing, TDS on supplier payments, and
   TCS on collections are all in scope. See [05-taxes.md](accounting/05-taxes.md) (revised priorities).
2. **Multi‑currency → real.** We transact in foreign currency. Exchange Rate Revaluation and a
   currency‑exchange rate master move from §3 "skip" to **scoped (later phase)**; the per‑document
   manual rate stays the default, live‑FX fetch stays optional.
3. **POS → deferred (flagged).** No multi‑terminal POS for now; keep the `is_pos` + multi‑mode‑payment
   simplification documented in [01-invoicing.md](accounting/01-invoicing.md) for when a counter appears.
4. **Subscription → build per judgment.** Treated as Phase 4 on‑demand (AMC/rentals are plausible for
   appliance trading); not on the critical path.
5. **Onboarding → assume migrating MSMEs with open balances.** As a SaaS selling to existing
   businesses, opening‑balance tooling is **urgent** and stays in Phase 1.

> Net effect on the roadmap: **Taxes (GST/TDS/TCS) rises to sit alongside onboarding in the early
> phases**, and multi‑currency correctness becomes a standing requirement for every new posting path.

---

## Sub‑module specs (the nine workspace cards)

| # | Sub‑module | Today | Net work | Spec |
|---|---|---|---|---|
| 1 | **Invoicing** | 🟢 core done | inclusive tax, opening tool, (POS deferred) | [01-invoicing.md](accounting/01-invoicing.md) |
| 2 | **Payments** | 🟢 core done | advances, dunning, payment request, statements | [02-payments.md](accounting/02-payments.md) |
| 3 | **Financial Reports** | 🟢 7 reports | registers, gross profit, ledger summaries, variance | [03-financial-reports.md](accounting/03-financial-reports.md) |
| 4 | **Accounts Setup** | 🟡 backend done | CoA UI, dimensions, opening balances, settings | [04-accounts-setup.md](accounting/04-accounts-setup.md) |
| 5 | **Taxes** | 🟡 templates done | TDS, tax rule, item tax template, inclusive | [05-taxes.md](accounting/05-taxes.md) |
| 6 | **Banking** | 🟢 import + match + create-from-unmatched | split allocations, statement opening/closing balance | [06-banking.md](accounting/06-banking.md) |
| 7 | **Budget** | 🟢 done | variance report, monthly distribution, dimensions | [07-budget.md](accounting/07-budget.md) |
| 8 | **Share Management** | 🔴 none | full sub‑module (lowest priority) | [08-share-management.md](accounting/08-share-management.md) |
| 9 | **Subscription** | 🔴 none | full sub‑module (build on demand) | [09-subscription.md](accounting/09-subscription.md) |
</content>
</invoke>
