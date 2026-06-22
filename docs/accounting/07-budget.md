# 07 · Budget

> Sub‑module of [ACCOUNTING_GAP_AND_PLAN.md](../ACCOUNTING_GAP_AND_PLAN.md). ERPNext workspace card: **Budget**.

## Status today — 🟢 functional

- **Budget** ([budget.py](../../backend/app/services/budget.py)): annual, per Fiscal Year (+ optional
  Cost Center), with account→amount rows; `action_if_annual_budget_exceeded` = Stop / Warn / Ignore.
- **Enforcement is real**: every expense GL row is validated against the budget in
  [gl.py](../../backend/app/services/gl.py) — Stop blocks the posting, Warn logs.
- **Frontend**: `/budgets` list + inline form (add account rows, submit/cancel).

This sub‑module already does the one thing budgets are for: stop over‑spend.

## Gaps vs ERPNext

| # | Gap | State | P | Why |
|---|---|---|---|---|
| 1 | **Budget Variance report** | 🔴 | 3 | Budget vs actual per account/cost center/period — the payoff of having budgets. |
| 2 | **Monthly Distribution** (seasonality) | 🔴 | 4 | Spread the annual budget across months so enforcement is monthly, not just annual. |
| 3 | **Budget against Project / Accounting Dimension** | 🟡 cost center only | 4 | Couples to dimensions ([04-accounts-setup.md](04-accounts-setup.md)). |
| 4 | **Budget on MR/PO/actual (3 control points)** | 🟡 actual only | 4 | ERPNext can also check budget at Material Request / Purchase Order commitment, not just actual GL. |

## Simplifications

- **Annual enforcement is the default**; Monthly Distribution is opt‑in seasonality, not mandatory.
- **Enforce on actual GL only** (current behavior) for Phase 1. Commitment‑stage checks (MR/PO) are a
  Phase‑later nicety, not core — SMBs care about "did we overspend", which is the actual‑GL check.
- **Budget dimensions** ride on the generic Accounting Dimension framework — don't special‑case Project.

## Build‑out

### Phase 2 — Make budgets visible
- ✅ **Budget Variance report** DONE (2026‑06‑19): for a fiscal year, per budgeted account —
  budgeted (sum of submitted Budget rows) vs actual (GL net debit‑credit in the FY window) vs
  variance & variance % (positive = under budget). `financial_reports.budget_variance` →
  `/reports/budget-variance` → a Budget Variance tab in `ReportsView.vue`. Verified live (Marketing
  94% / Office Rent 85% / Salary 92% under budget on the demo books). *Acceptance met:* the "actual"
  column is the GL balance per account for the FY.
- ⏳ Monthly‑distribution pro‑rating (variance by month) — later, with Monthly Distribution.

### Phase 2 — Monthly Distribution *(engine master + enforcement tweak)*
- **Monthly Distribution** master (engine): name + 12 month‑percentage rows (sum = 100).
- Extend budget enforcement to pro‑rate the annual amount by month‑to‑date distribution when set.
- *Acceptance:* with a front‑loaded distribution, an early‑year overspend that's within the annual
  budget can still trip a Stop if it exceeds the month‑to‑date allocation.

### Later — dimension budgets
- Once Accounting Dimensions exist, allow a budget scoped to a dimension value (e.g. budget per Project).

## Engine vs bespoke
- **Engine:** Monthly Distribution master.
- **Bespoke:** the enforcement check in `gl.py` (exists — extend for monthly), the Budget document
  (exists), the variance report (read‑only).
</content>
