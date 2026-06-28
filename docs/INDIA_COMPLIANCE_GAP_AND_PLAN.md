# India Compliance — Build Plan (GST + statutory, multi-tenant SaaS)

**Scope:** make OptiReach a **multi-tenant SaaS** that keeps any Indian MSME GST-compliant — correct GST on
every document, GST-compliant invoices, the monthly **returns** (GSTR-1/3B), **e-invoice** and **e-way
bills**, **reverse charge**, **GSTR-2B reconciliation**, and the TDS/TCS already in place — **eventually
covering the full GST spectrum** (regular + composition, monthly + QRMP, B2B/B2C, SEZ/export, e-commerce
TCS), **configurable per tenant**, and with **live portal/GSP automation** as a planned phase. Modelled on
ERPNext + the Frappe **India Compliance** app.
**Status:** 🟡 plan (2026-06-23), **build on hold** — GST *core* exists; the *compliance layer* (HSN,
returns, e-docs, GSP integration) does not.
**Designed:** 2026-06-23.

> **SaaS framing (owner, 2026-06-23):** this is a product for *many* MSMEs, so we **cannot permanently skip**
> a GST case — some tenant will need each one. The lever is **per-tenant configuration + sensible
> sequencing**, not omission: build the broad foundation first, gate edge cases behind per-company settings,
> and layer the **live GSP/IRP/NIC integration** (owner wants portal automation) on top of a data/JSON layer.
> House rules still hold: reuse the existing tax engine / GL / print system — no new posting engine.
> ERPNext's India GST lives in a **separate app** (`india-compliance`), so this draws on that app + GST law,
> not the core `reference/` tree (UAE/US/etc. only).

---

## 0. Plain-language summary (read this first)

"Indian compliance" for a distributor is mostly **GST** plus a bit of **TDS/TCS**. Three jobs:

1. **Put the right tax on every bill** and print a **GST-compliant invoice** (both GSTINs, HSN code per
   line, place of supply, CGST/SGST/IGST split, amount in words). *← we mostly do the tax; we don't yet
   print all the legally-required fields or carry HSN.*
2. **Hand the government the monthly numbers** — **GSTR-1** (every sale, grouped the way the portal wants)
   and **GSTR-3B** (the summary + input-tax-credit). *← not built; this is the headline gap.*
3. **Move goods legally** — an **e-way bill** when you transport > ₹50,000 of goods, and (above a turnover
   threshold) an **e-invoice** with a government IRN/QR. *← not built.*

The good news: the **hard tax math already works** — GSTIN-based auto-pick of IGST (inter-state) vs
CGST+SGST (intra-state), tax templates, MRP-inclusive tax, per-item GST slabs (Item Tax Template), and
TDS/TCS. So compliance is mostly **adding the missing fields (HSN, place of supply), a compliant invoice
print, and reading the GL/invoices into the return formats** — not re-doing tax.

**Stance on e-docs (SaaS):** build the **data/JSON layer first** (works for every tenant and is the
foundation), then add **live GSP/IRP/NIC integration** so tenants can push e-invoices, e-way bills and
returns from inside the app (the owner wants portal automation). The live layer is **pluggable** (a GSP
provider abstraction + per-tenant credentials), so different GSPs/sandbox/production can be configured —
not a permanent omission, just a later phase that sits on the data layer.

---

## 1. What an Indian MSME distributor actually needs

| Area | What it is | Priority for a distributor |
|---|---|---|
| **GST on invoices** | Correct CGST/SGST/IGST by place of supply | ✅ have |
| **HSN/SAC codes** | 4–8 digit goods code on every taxable line (legally required; drives GSTR-1 HSN summary) | **must** |
| **GST-compliant tax invoice** | Both GSTINs, HSN, place of supply, tax split, RCM flag, amount in words | **must** |
| **GSTR-1** | Monthly outward-supply return (B2B, B2C-large, B2C-small, HSN summary, document summary) | **must** |
| **GSTR-3B** | Monthly summary return (outward tax + eligible ITC) | **must** |
| **E-Way Bill** | Required to transport goods > ₹50k — a distributor's daily reality | **high** |
| **Reverse Charge (RCM)** | Buyer pays GST on certain inward supplies (freight/GTA, legal, unregistered) | **medium** |
| **E-Invoice (IRN + QR)** | Government-registered invoice; **mandatory only if AATO > ₹5 cr** | **threshold** |
| **GSTR-2A/2B reconciliation** | Match purchases to what suppliers filed (protect ITC) | **medium** |
| **GST on advances** | GST payable when you receive an advance before supply | **low/medium** |
| **TDS/TCS** | Withhold/collect tax at source + returns (26Q) + Form 16A | ✅ mostly have |
| **Nil/Exempt/Non-GST** | Mark non-taxable supplies so returns are correct | **must (small)** |

---

## 2. What we already have (don't rebuild)

- **GSTIN** on Company, Customer, Supplier (`tax_id`), with **state-code comparison** (`gstin[:2]`) that
  auto-selects **IGST** (inter-state) vs **CGST+SGST** (intra-state) tax templates — `resolve_tax_template`
  in `accounts_masters.py`.
- **Tax Template** (Sales/Purchase) + **Tax Category** (inter-state) + the faithful **Taxes & Totals**
  engine (per-item chaining, multi-currency, rounding), incl. **MRP-inclusive** tax.
- **Item Tax Template** — per-item GST-slab override (5/12/18% on one invoice).
- **Output CGST/SGST/IGST + Input GST** accounts in the COA.
- **TDS/TCS** — Tax Withholding Category + deduction posting (+ some reports).
- A themed **PDF/print** system (Sales/Purchase Invoice) to extend for the GST invoice format.

---

## 3. The gaps (what to build)

1. **HSN/SAC on Item** (+ optional default GST rate / `gst_treatment` = Taxable | Nil-rated | Exempt |
   Non-GST). Carried onto invoice lines. *Foundation for legal invoices + GSTR-1 HSN summary.*
2. **Place of Supply** on Sales/Purchase Invoice (a state; defaults from the party's GSTIN state, editable —
   matters for services and for GSTR-1).
3. **GST-compliant tax invoice print** — supplier+recipient GSTIN, HSN per line, place of supply,
   taxable value + CGST/SGST/IGST columns, reverse-charge marker, "amount in words", invoice-type label.
4. **GSTR-1 report** — outward supplies grouped: **B2B**, **B2C (large/small)**, **HSN-wise summary**,
   **document summary** — read from submitted Sales Invoices. + optional **GSTR-1 JSON** export.
5. **GSTR-3B report** — section 3.1 (outward taxable/zero/nil/exempt) + 3.2 (inter-state to unregistered) +
   eligible **ITC** (from Purchase Invoices) — a summary the CA files.
6. **Reverse Charge (RCM)** — a flag on Purchase Invoice: book the GST liability **and** the ITC (and a
   self-invoice for unregistered purchases) so net ITC is right.
7. **E-Way Bill** — generate the **EWB JSON payload** (transporter, vehicle, from/to, HSN, value) for upload;
   live NIC API **deferred**.
8. **E-Invoice (IRN/QR)** — generate the **e-invoice JSON** (Schema 1.1) for B2B; live IRP/GSP API **deferred**;
   only relevant above the ₹5 cr turnover threshold.
9. **GSTR-2A/2B reconciliation** — import portal data and match to the purchase register. *(Optional/defer.)*
10. **GST on advances** — GST liability on advance receipts, adjusted on the later invoice. *(Optional.)*

---

## 4. Per-tenant configuration & sequencing (SaaS: cover all cases, sequenced)

Nothing is permanently cut — each case is **gated by a per-company GST Settings flag** and **sequenced**,
so a tenant that needs it can turn it on without re-architecting.

| Case | How it's handled |
|---|---|
| **Registration type** (Regular vs **Composition**) | Per-tenant flag; Composition tenants get composition invoice/return behaviour (later phase, off by default). |
| **Filing cadence** (Monthly vs **QRMP**) | Per-tenant flag; returns surface honours it. |
| **E-Invoice (IRN/QR)** | Per-tenant `e_invoice_applicable` flag (set by turnover band). JSON generator first, **live IRP/GSP** later. |
| **E-Way Bill** | Per-tenant `e_way_bill_applicable`. JSON generator first, **live NIC** later. |
| **GSP/IRP/NIC live API** (auto e-invoice/e-way/return push) | **Pluggable provider** + per-tenant credentials; built on the data/JSON layer (later phase). |
| **GSTR-2A/2B reconciliation** | Build the matcher; portal **pull** via GSP in the live phase, **file upload** before that. |
| **SEZ / Export (with/without payment)**, **e-commerce TCS u/s 52**, **RCM** | Modelled as GST-treatment/flow flags on the document; phased in. |
| **e-invoice cancel/amend, e-way Part-B vehicle update** | Supported via the live API phase; before that, manage on the portal. |
| **GST Settings** | A real **per-company settings** record (not a few stray fields) — see §5. |

The only genuine *omissions* are non-GST statutory areas with no module yet: **payroll (PF/ESI/PT)** —
out of scope until an HR/Payroll module exists.

---

## 5. Data model (fields + masters + reports)

**Per-company GST Settings** (a record per tenant — the SaaS config surface):
`registration_type` (Regular | Composition), `gst_state` (from GSTIN), `filing_cadence` (Monthly | QRMP),
`e_invoice_applicable`, `e_way_bill_applicable`, `is_sez`, GSP provider + credentials (later phase).

**Fields (small migrations):**
- **Item:** `hsn_sac_code` (Data), `gst_treatment` (Taxable | Nil-rated | Exempt | Non-GST).
- **Sales/Purchase Invoice:** `place_of_supply` (state), `is_reverse_charge` (Check, purchase),
  `gst_category` (Registered | Unregistered | SEZ | Export | Composition), `hsn_sac_code` snapshot on the
  **invoice item** (copied from Item at billing).

**Reports (read-only services + a Compliance reports surface):** GSTR-1, GSTR-3B, HSN summary, (later)
GSTR-2B reconciliation, TDS 26Q.

**Bespoke vs engine:** the GST math/RCM posting + return computation are **bespoke** (read GL/invoices,
reuse the tax engine + GL). HSN/`gst_treatment` are just **fields on existing masters/docs**. E-way-bill /
e-invoice JSON builders are **bespoke read-only generators**.

**Decision rule:** posts GL / computes statutory figures → bespoke; a field on a master → add the column;
a filing artifact → read-only generator/report.

---

## 6. Phased build plan

### Phase 1 — Invoice GST completeness *(foundation; gating)*
- **HSN/SAC** + `gst_treatment` on Item, snapshotted onto invoice lines.
- **Place of Supply** on Sales/Purchase Invoice (default from party GSTIN state).
- **GST-compliant tax-invoice print** (both GSTINs, HSN, POS, CGST/SGST/IGST split, RCM marker, amount in
  words) — extend the existing PDF/print slice.
- *Acceptance:* an intra-state invoice prints CGST+SGST with HSN per line + place of supply; an inter-state
  one prints IGST; both show both GSTINs and amount in words.

### Phase 2 — GST returns *(the headline value)*
- **GSTR-1** report: B2B, B2C (large/small), **HSN-wise summary**, document summary — from submitted Sales
  Invoices; + **GSTR-1 JSON** export (portal schema).
- **GSTR-3B** report: outward tax summary + eligible ITC from Purchase Invoices.
- A **Compliance → GST Returns** reports surface (period picker, drill-down, export).
- *Acceptance:* for a month, GSTR-1 totals tie to the sales register and the Output GST ledger; GSTR-3B
  3.1 tax matches; HSN summary sums to taxable value.

### Phase 3 — Reverse charge + advances
- **RCM** flag on Purchase Invoice → post GST liability + ITC (and a self-invoice for unregistered).
- **GST on advances** (optional) — liability on advance receipts, adjusted at invoicing.

### Phase 0 (cross-cutting) — per-company **GST Settings** — ✅ DONE (2026-06-28)
A tenant config record everything below reads. **Built:** `GstSettings` stored as a per-company JSON blob
under the `gst_settings` `SystemSetting` key (no new table — mirrors the print/branding profile) with
`registration_type` (Regular | Composition), `filing_cadence` (Monthly | QRMP), `e_invoice_applicable`,
`e_way_bill_applicable`, `is_sez`. **GSTIN + place-of-supply state are derived from `Company.tax_id` on
read** (single source of truth) via a new `app/core/gst_states.py` (the 37 GST state codes + GSTIN→state /
`NN-State` helpers, reused by Phase 1 place-of-supply). `GET`/`PUT /gst-settings`; frontend
`/gst-settings` page (Settings + Accounting→Taxes links). Tests: 4 unit (state derivation) + 3 integration
(defaults/save/reload, validation, GSTIN-derived state). The GSP-credentials slot lands with Phase 5.

### Phase 4 — E-documents (data/JSON layer)
- **E-Way Bill JSON** generator (transporter/vehicle/from-to/HSN/value), gated by `e_way_bill_applicable`.
- **E-Invoice JSON** (Schema 1.1) generator for B2B, gated by `e_invoice_applicable`.

### Phase 5 — Live GSP/IRP/NIC integration *(portal automation — owner wants this)*
- A **pluggable GSP provider** abstraction + per-tenant credentials (sandbox/production).
- Push **e-invoice → IRN + signed QR** (with cancel/amend), **e-way bill → EWB no.** (with Part-B updates),
  and **GSTR-1/3B filing** + **GSTR-2B pull** through the GSP.
- Built on the Phase-4 data layer, so a tenant without GSP creds still gets JSON export.

### Phase 6 — Reconciliation & the long tail (per-tenant, as demand appears)
- **GSTR-2B reconciliation** (matcher + portal pull), **Composition** scheme flows, **QRMP**,
  **SEZ/Export** (with/without payment), **e-commerce TCS u/s 52**, **TDS 26Q + Form 16A** reports.

### Out of scope (no module yet)
- Payroll statutory (PF / ESI / Professional Tax) — needs an HR/Payroll module first.

---

## 7. Decisions captured (owner, 2026-06-23)
1. **This is a multi-tenant SaaS for MSMEs → cover all GST cases**, configurable per tenant — don't
   permanently omit e-invoice, composition, QRMP, SEZ/export, e-commerce TCS; gate them behind per-company
   **GST Settings** and sequence them (Phase 6 long tail).
2. **E-invoice is in scope** (not deferred on turnover) — every tenant can enable it via
   `e_invoice_applicable`; the JSON generator (Phase 4) lands first, the live IRP push (Phase 5) after.
3. **Portal/GSP automation is wanted** → Phase 5 builds a pluggable GSP/IRP/NIC integration on top of the
   Phase-4 data layer (e-invoice IRN/QR, e-way bill, GSTR push + GSTR-2B pull).
4. **Build = "just the plan for now"** — plan approved as the design; **build is on hold** until the owner
   says go.

> **Recommended build order when greenlit:** Phase 0 (GST Settings) → Phase 1 (HSN + place of supply + GST
> invoice print) → Phase 2 (GSTR-1 + GSTR-3B, file-ready) → Phase 3 (RCM) → Phase 4 (e-invoice + e-way JSON)
> → Phase 5 (live GSP/IRP/NIC) → Phase 6 (reconciliation + composition/QRMP/SEZ/TCS long tail). Foundation
> is broad and shared; tenant-specific cases ride on per-company settings.

> **Status:** 🟡 **Plan approved, build on hold.** Resume Phase 0/1 on the owner's go-ahead.
