# 06 · Banking

> Sub‑module of [ACCOUNTING_GAP_AND_PLAN.md](../ACCOUNTING_GAP_AND_PLAN.md). ERPNext workspace card: **Banking**.

## Status today — 🟡 report only, no statement workflow

- **Bank Account** master — ✅ (links a GL account; IBAN, is_default).
- **Bank Reconciliation report** — ✅ read‑only ([financial_reports.py](../../backend/app/services/financial_reports.py)):
  lists uncleared payments/JEs for a GL account, compares book vs. bank balance.
- **Clearance date** — ✅ stored on Payment Entry and Journal Entry (set manually).
- **No statement import, no auto‑matching, no bank‑transaction model.** The daily banking workflow
  (download statement → match → clear) doesn't exist yet.

## Gaps vs ERPNext

| # | Gap | State | P | Why |
|---|---|---|---|---|
| 1 | **Bank Reconciliation card wiring** | 🟡 placeholder | 0 | The report tab exists; the card just needs to point at `/reports?tab=bank-recon`. |
| 2 | **Bank Transaction model** | 🔴 | 2 | An imported statement line that can be matched to a payment/JE. The spine of real bank rec. |
| 3 | **Bank Statement Import** | 🔴 | 2 | Upload CSV/XLS, map columns (date/amount/ref/description) → Bank Transactions. |
| 4 | **Bank Reconciliation Tool** | 🔴 | 2 | Interactive match: suggest payments/JEs per transaction; create a Payment Entry/JE for unmatched lines; set clearance. |
| 5 | **Bank Clearance** (bulk set clearance dates) | 🟡 manual | 3 | Tool to set clearance dates across many vouchers at once. |
| 6 | **Bank Guarantee** | 🔴 | 5 | Record guarantees issued/received. Niche — defer. |
| 7 | **Cheque Print Template** | 🔴 | 5 | Cheque layout printing. Defer. |

## Simplifications

- **One reconciliation path.** Bank Transaction + Bank Reconciliation Tool subsume the old manual
  clearance‑date entry; keep the read‑only report as the "where do we stand" view.
- **Matching is suggest‑then‑confirm**, not ML. Match by amount + date window + reference string;
  the user confirms. No fuzzy‑learning mapping engine beyond a saved column‑map per bank format.
- **Skip Bank Guarantee, Cheque Print, Invoice Discounting, Payment Order** until explicitly needed.

## Build‑out

### Phase 0 — Wire the existing report
- Point the **Bank Reconciliation** workspace card at `/reports?tab=bank-recon`.
- *Acceptance:* card opens the working report; no `planned: true` left.

### Phase 2 — Statement import + reconciliation *(bespoke — creates entries)*
Data model (new):
- **Bank Transaction**: `date, bank_account_id, description, reference_no, deposit, withdrawal, currency, status (Unreconciled/Reconciled), allocated_amount`.
- **Bank Transaction ↔ voucher allocations** (child): links to Payment Entry / Journal Entry with allocated amount.
- **Bank Statement Import**: upload + a saved **column‑mapping** per bank → rows become Bank Transactions.

Flow:
1. Import statement → Bank Transactions (Unreconciled).
2. Reconciliation Tool lists each transaction with **suggested** matching vouchers (amount + date ± window + ref match).
3. User confirms a match (sets clearance date on the voucher, marks transaction Reconciled) **or** creates a new Payment Entry/JE for an unmatched line (then auto‑matches it).

*Services:* `bank_transaction.py` (import + model), `bank_reconciliation.py` (matching + create‑entry + clearance). **Bespoke** — it sets clearance and can post new entries.

*Acceptance:* import a 100‑line statement → match the auto‑suggested ones → create entries for the rest → the Bank Reconciliation report shows zero uncleared and book = bank.

### Phase 3 — Bank Clearance bulk tool
- Select a date range + account → set clearance dates in bulk for already‑matched vouchers.

## Engine vs bespoke
- **Engine:** Bank, Bank Account, Bank Account Type (if needed), the per‑bank column‑mapping master.
- **Bespoke:** statement import parsing, the reconciliation/matching tool, entry creation, clearance setting.
</content>
