# 02 · Payments

> Sub‑module of [ACCOUNTING_GAP_AND_PLAN.md](../ACCOUNTING_GAP_AND_PLAN.md). ERPNext workspace card: **Payments**.

## Status today — 🟢 core complete

- **Payment Entry** ([payment_entry.py](../../backend/app/services/payment_entry.py)): Receive / Pay /
  Internal Transfer; party + bank/cash GL rows; allocation against invoices; deductions (bank
  charges, write‑off); `unallocated_amount`; clearance date for bank rec.
- **Payment Reconciliation** ([payment_reconciliation.py](../../backend/app/services/payment_reconciliation.py)):
  fetch a party's outstanding invoices + unallocated payments, apply allocations, adjust outstanding.
- **Frontend**: `/payment-entries` (list + inline form with live allocation), `/payment-reconciliation` (two‑column matcher).

## Gaps vs ERPNext

| # | Gap | State | P | Note |
|---|---|---|---|---|
| 1 | **Advance payments first‑class** | 🟡 field only | 1 | `advance_paid` exists on invoices, but no advance‑receipt workflow, no allocation of an on‑account payment as an advance on a *future* invoice, no tax‑on‑advance. Trading runs on deposits. |
| 2 | **Dunning** (overdue reminders) | 🔴 | 3 | Reminder doc with interest + fee + letter text per Dunning Type. |
| 3 | **Process Statement of Accounts** | 🔴 | 3 | Bulk‑email periodic AR statements to customers (PDF per party, date‑ranged). |
| 4 | **Payment Request** | 🔴 | 3 | A request‑for‑payment tied to an invoice/order, with email + (optional) gateway link. |
| 5 | **Payment Order** (bank disbursement file) | 🔴 | 5 | Batches payment refs into a bank file. **Defer** — niche for SMB. |
| 6 | **Unreconcile Payment** | 🔴 | 4 | Reverse a prior allocation. Useful safety valve; low frequency. |
| 7 | **Process Payment Reconciliation** (bulk, background) | 🔴 | 5 | Our single‑party tool is enough at our scale. Skip the batch processor. |

## Simplifications

- **No Payment Ledger** — outstanding lives on the invoice (master §3.1). All payment logic adjusts
  invoice `outstanding_amount` directly.
- **No Payment Order / bank file export** until a bank integration is actually required.
- **Dunning** = one document type + a `Dunning Type` master (engine‑served); skip multi‑language
  letter tables — one body + one closing text is enough.

## Build‑out

### Phase 1 — Advances first‑class ✅ DONE (2026‑06‑19)
- ✅ An on‑account Payment Entry (no reference) already credits the party's receivable/payable, so the
  party is genuinely "in credit" (ERPNext's default **party‑account advance model**) — and Payment
  Reconciliation already allocates it to invoices. The loop‑closing UX was the gap: the **invoice
  detail now lists the party's available advances and applies them in one click** (reuses the
  reconciliation service — links the payment + drops the invoice outstanding; **no new GL**, since
  the credit is already on the party account). Verified live: ₹5k advance applied to an invoice
  dropped its outstanding by exactly ₹5k; cancelling the advance restored it.
- **Deliberate simplification:** we do **not** post advances to a separate advance account with a
  reclassification JE on allocation (an ERPNext option). The party‑account model is simpler, correct,
  and keeps AR/AP aging consistent — matches our "drop the ceremony" stance.
- **GST‑on‑advance: out of scope for goods.** India's Notification 66/2017 removed GST‑on‑advance for
  goods (it remains only for *services*). For an appliance/goods trader, GST is due at the tax invoice,
  not the deposit — so no advance‑tax posting is needed. Revisit only if the business sells services.

### Phase 3 — Collections tooling
- **Dunning** (*bespoke for the interest JE; engine for the master*):
  - `Dunning Type` master (rate, fee, account) — **engine descriptor**.
  - `Dunning` document — collects overdue invoices for a party, computes interest, optionally posts an interest JE, renders a PDF letter. **Bespoke**.
- **Process Statement of Accounts** (*bespoke read + render*): date‑ranged AR statement per customer → PDF → email. Reuse the print system.
- **Payment Request** (*mostly engine + email hook*): a light document linking to an invoice/order with an amount and status; email a link. Skip the payment‑gateway integration initially.
- *Acceptance:* an overdue customer generates a dunning letter with correct interest; a statement PDF lists all open items for a date range.

## Engine vs bespoke
- **Engine:** Mode of Payment, Dunning Type, Payment Terms Template.
- **Bespoke:** Payment Entry, advance allocation, Dunning (interest posting), Statement of Accounts (render), Payment Request (status + email).
</content>
