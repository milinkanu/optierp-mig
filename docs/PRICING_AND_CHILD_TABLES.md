# Child Tables & the Pricing Engine — a plain-language guide

This explains two things we recently built on top of "the machine" (the metadata
engine):

1. **Child tables** — letting a screen hold a *list of line items*, not just boxes.
2. **The pricing engine** — working out the right price/discount on a sales line.

It's written to be readable without knowing the code. The developer details are
at the very end.

---

## Part 1 — Child tables ("a screen with a list inside it")

### What it is
Most simple screens are just "fill in some boxes and Save" (a Territory has a
name and a parent — that's it). But some screens need a **list** inside them:

- A **Product Bundle** = one bundle + a *list of component items*.
- A **Blanket Order** = one contract + a *list of items and agreed rates*.
- A **Promotional Scheme** = one promo + a *list of "buy this much → get this %" tiers*.

Think of a paper form that has a **table you can add rows to** in the middle.
That repeating table is a "child table"; the form around it is the "parent".

### Why we needed it
Before this, the machine could only build **flat** screens (just boxes). Anything
with a line-item table had to be hand-coded from scratch — exactly the slow,
duplicated work the machine was meant to kill. Three of the pricing screens
(Bundle, Blanket Order, Promotional Scheme) are *useless* without their list. So
we taught the machine to handle lists **once**, and now any screen can have one.

### How it works (simple version)
The recipe card for a screen can now say *"this screen also has a grid called
Components, and each row has an Item, a Qty, and a Description."* From that one
declaration the machine automatically:

- **draws an editable grid** in the form (with **+ Add row** and a ✕ to remove rows),
- **saves** each row, linked to its parent, in order,
- on edit, **replaces** the rows with whatever you left in the grid,
- **deletes** the rows automatically when you delete the parent.

So adding a "screen with a list" is still just a recipe card — no hand-built table.

### What it looks like
```
Product Bundle: "Diwali Combo"
  Bundle Components
  ┌───────────────────┬──────┬───────────────┐
  │ Item              │ Qty  │ Description    │   ← child grid (add/remove rows)
  ├───────────────────┼──────┼───────────────┤
  │ Mixer Grinder     │ 1    │ main unit      │
  │ Spare Jar         │ 2    │ free jars      │
  └───────────────────┴──────┴───────────────┘
  [ + Add row ]
```

---

## Part 2 — The pricing engine ("what should this line actually cost?")

### What it is
When you put an item on a sales order, its price isn't just the catalogue price.
Real businesses run **discounts, contracts, coupons, freight, bundles and
promotions**. The pricing engine figures out the final number for each line, using
six tools that you set up once and that then apply automatically.

The six tools (each is a screen you can create in the UI):

| Tool | In one line | Example |
|---|---|---|
| **Pricing Rule** | a discount or price override | "10% off Mixers for Wholesale customers" |
| **Promotional Scheme** | buy-more-save-more tiers | "Buy 10 → 5% off, buy 50 → 10% off" |
| **Coupon Code** | a code the customer redeems | "DIWALI10 = 10% off, max 100 uses" |
| **Shipping Rule** | a freight charge | "₹50 shipping, free over ₹1,000" |
| **Blanket Order** | a long-term contract rate | "Acme buys this item at ₹999 all year" |
| **Product Bundle** | one SKU = several items | "Combo = Mixer + 2 Jars" |

### Why we built it
Without it, every order line is just the fixed item price — no way to run a sale,
honour a customer contract, give a coupon, or charge shipping. These are
table-stakes for any selling system, and they're exactly the ERPNext features you
asked to replicate.

### How it works — the pipeline
For **each line** on a Quotation or Sales Order, the engine runs this, in order:

```
1. Start with a BASE price
   ├─ Is there a Blanket Order (contract) rate for this customer + item?  → use it
   └─ otherwise → the item's Price List rate (or its standard rate)

2. DISCOUNT the line
   ├─ best matching Pricing Rule        ┐  whichever gives the
   └─ best matching Promotional Scheme  ┘  LOWER price wins

3. Whole-order extras
   ├─ Coupon code on the order   → a % off the order total
   └─ Shipping Rule on the order → adds a freight charge line
```

Two important, deliberate choices:

- **Pricing happens on the Quotation and Sales Order** (where the price is decided),
  **not on the Sales Invoice** — the invoice inherits the order's prices, so a
  discount is never applied twice.
- **Product Bundle** is a master you can set up today (one SKU listing its
  components). *Exploding* a bundle into its component lines at billing time is a
  separate follow-up that isn't wired yet — noted honestly so there's no surprise.

### A worked example
Item base price **₹2,850**, customer is in the "Wholesale" group, ordering **qty 60**:

1. No blanket contract → base = **₹2,850**.
2. A Pricing Rule "Wholesale −10%" gives ₹2,565; a Promotional Scheme tier "buy 50 → −12%"
   gives ₹2,508. The **lower wins → ₹2,508**.
3. The order also has coupon "SAVE5" (−5% on the total) and a Shipping Rule
   (₹50, but the order is over ₹1,000 so shipping is **free**).

Final line rate: **₹2,508**, with the 5% coupon applied to the order total and no
freight charge. Every step is just data the user set up — no code per deal.

---

## Where it lives (developer reference)

### Child tables
- **Declare a grid:** add a `ChildSpec(field, label, model, fk_column, fields)` to a
  descriptor's `children` in [backend/app/registry/descriptors.py](../backend/app/registry/descriptors.py).
  (`ChildSpec` is defined in [backend/app/registry/base.py](../backend/app/registry/base.py).)
- **Engine handling:** [backend/app/services/registry.py](../backend/app/services/registry.py)
  generates the child row model, writes rows (FK + `idx`) on create, wholesale-replaces
  them on update, includes them in `GET`/responses, and exposes the grid config via `/meta`.
- **Frontend grid:** [frontend/src/components/shared/ChildGrid.vue](../frontend/src/components/shared/ChildGrid.vue),
  rendered by [frontend/src/views/generic/GenericFormView.vue](../frontend/src/views/generic/GenericFormView.vue).
- Child rows have **no separate permissions/RLS** — they're reached only through the
  parent (which is company-checked), matching the existing invoice/order line tables.

### Pricing engine
One small service per tool, plus a single entry point wired into the order services:

| Tool | Service |
|---|---|
| Pricing Rule + Promotional Scheme combine here (entry point) | [backend/app/services/pricing.py](../backend/app/services/pricing.py) → `apply_selling_pricing` |
| Promotional Scheme tiers | [backend/app/services/promotion.py](../backend/app/services/promotion.py) |
| Coupon Code | [backend/app/services/coupon.py](../backend/app/services/coupon.py) |
| Shipping Rule | [backend/app/services/shipping.py](../backend/app/services/shipping.py) |
| Blanket Order (contract rate) | [backend/app/services/blanket.py](../backend/app/services/blanket.py) |

- **Wired into** the line loops of [backend/app/services/quotation.py](../backend/app/services/quotation.py)
  and [backend/app/services/sales_order.py](../backend/app/services/sales_order.py): base rate
  (blanket → item price) → `apply_selling_pricing` → coupon (order discount) → shipping (charge row).
- The match/calc helpers (`rule_matches`, `apply_rule`, `best_tier_discount`,
  `coupon_invalid_reason`, `shipping_amount_for`) are **pure functions**, unit-tested in
  `backend/tests/unit/test_pricing.py`, `test_promotion.py`, `test_coupon.py`, `test_shipping.py`.
- The pricing-rule/scheme/bundle/blanket masters are **engine-served** (created at
  `/m/pricing-rule`, `/m/product-bundle`, etc.) — so their screens cost only a descriptor.

### The screens (DocTypes)
Pricing Rule, Coupon Code, Shipping Rule, Product Bundle, Blanket Order, Promotional
Scheme — models in [backend/app/models/selling.py](../backend/app/models/selling.py),
migrations `0011`–`0017`, all reachable from the **Selling workspace → Items & Pricing**.
