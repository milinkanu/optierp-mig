# 01 · Invoicing

> Sub‑module of [ACCOUNTING_GAP_AND_PLAN.md](../ACCOUNTING_GAP_AND_PLAN.md). ERPNext workspace card: **Invoicing**.

## Status today — 🟢 core complete

Sales Invoice and Purchase Invoice are full, hand‑coded services with GL posting, returns,
cycle links, taxes, and PDF. This is the most mature part of the module.

- **Sales Invoice** ([sales_invoice.py](../../backend/app/services/sales_invoice.py)): Dr Receivable /
  Cr Income + taxes + rounding; SO/DN cycle links; credit notes (`is_return`); derived status; outstanding tracking; PDF.
- **Purchase Invoice** ([purchase_invoice.py](../../backend/app/services/purchase_invoice.py)): Cr Payable /
  Dr Expense + taxes; PO/PR cycle links; `stock_received_but_not_billed` for perpetual inventory; debit notes; PDF.
- **Frontend**: list + multi‑tab form (Details/Payments/Address/Terms/More Info) at `/sales-invoices`, `/purchase-invoices`.

## Gaps vs ERPNext

| # | Gap | State | P | Note |
|---|---|---|---|---|
| 1 | **Inclusive taxes** (`included_in_print_rate`) | 🔴 blocked | 1 | Engine raises `ValidationError`. MRP‑inclusive pricing is normal. Detail lives in [05-taxes.md](05-taxes.md); invoicing just consumes it. |
| 2 | **Opening Invoice Creation Tool** | 🔴 | 1 | Bulk‑enter outstanding sales/purchase invoices at go‑live (single screen, many rows → many draft+submit invoices with `is_opening`). |
| 3 | **"More Info" + "Payments (POS)" form tabs** | 🟡 stubbed | 3 | Two tabs in the form say "coming soon". Wire More Info (project, remarks, letterhead); POS tab gates on §POS below. |
| 4 | **POS Invoice subsystem** | 🔴 | 4 | ~15 ERPNext doctypes. **Defer** unless a retail counter is in scope — see simplification. |
| 5 | **Deferred revenue** (recognize income over time) | 🔴 | 5 | Only with Subscription — see [09-subscription.md](09-subscription.md). Skip for now. |
| 6 | **Sales/Purchase timesheet billing, advances child table** | 🟡 | 4 | Advances handled in [02-payments.md](02-payments.md); timesheet billing out of scope. |

## Simplifications (copy value, drop ceremony)

- **POS = `is_pos` flag + multi‑mode payment child table**, not 15 doctypes. Skip POS Opening/Closing
  Entry, Merge Log, Cashier Closing, POS Settings. A POS sale is just a Sales Invoice that is paid
  immediately across one or more modes of payment. Build only if a physical counter exists.
- **Opening invoices** reuse the existing invoice service with an `is_opening` flag that posts
  directly against a temporary opening account — no separate "opening" document type.
- **No deferred revenue engine** until subscriptions exist (see master §3.6).

## Build‑out

### Phase 1 — Onboarding & inclusive tax
- **Inclusive taxes**: extend [taxes_and_totals.py](../../backend/app/services/taxes_and_totals.py) to
  back‑compute net rate when `included_in_print_rate` is set (faithful ERPNext algorithm). *Bespoke — touches the posting math.*
- ✅ **Opening Invoice Creation Tool** DONE (2026‑06‑19):
  - *Backend:* `is_opening` on Sales/Purchase Invoice (migration 0039); when set, the invoice skips
    tax resolution and books its single line to the company's **Temporary Opening** account
    (`account_type="Temporary"`), and `make_gl_entries` is called with `is_opening=True`. The bulk
    tool `opening_invoice.py` (`POST /opening-invoices`) takes rows `(party_id, outstanding_amount,
    posting_date?, due_date?, bill_no?)` and creates+submits one opening invoice each. Excluded from
    the Sales/Purchase Register; included in AR/AP aging.
  - *Frontend:* grid tool under Setup (`/opening-invoices`) — sales/purchase toggle, **Create
    Missing Party** (find‑or‑create customer/supplier by name), per‑row item name / posting / due
    dates, and **CSV Download (template) / Upload** for bulk migration (client‑side parse →
    populates the grid for review, auto‑enables Create Missing Party). Full ERPNext‑tool parity
    except the Company selector (deliberately dropped — single‑company).
  - *Verified:* integration test (2 opening receivables → AR ₹75k, register empty, Temporary Opening
    credited ₹75k) + live UI (created & cancelled a real opening invoice).
  - *Account opening balances (cash/bank/capital):* a normal Journal Entry against Temporary Opening
    — no new code needed.
- **Wire "More Info" tab** (project, remarks, letterhead, cost center default).

### Phase 4 — POS (conditional)
- Add `is_pos`, a `payments` child table (mode_of_payment, amount), and an immediate Payment Entry on submit.
- *Acceptance:* a POS sale posts revenue + receipt + leaves zero outstanding in one action.

## Engine vs bespoke
Invoices are **bespoke** (GL posting). The Opening Invoice Tool and POS are **bespoke** too. No
engine descriptors here — the only masters are tax templates ([05](05-taxes.md)) and terms.
</content>
