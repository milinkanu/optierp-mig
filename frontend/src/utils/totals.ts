// Client-side preview of ERPNext-style document totals. The backend recomputes
// authoritatively on save; this mirrors the standard charge-type math so the
// create form shows a faithful live Grand Total / Rounded Total / In Words.

export interface TotalsItem {
  qty?: number | string | null;
  rate?: number | string | null;
}
export interface TotalsTax {
  charge_type: string;
  rate?: number | string | null;
  tax_amount?: number | string | null;
  row_id?: number | string | null;
}
export interface TotalsDiscount {
  apply_discount_on: string; // "Grand Total" | "Net Total"
  additional_discount_percentage?: number | string | null;
  discount_amount?: number | string | null;
}
export interface DocTotals {
  totalQty: number;
  netTotal: number;
  totalTaxes: number;
  discountAmount: number;
  grandTotal: number;
  roundedTotal: number;
  roundingAdjustment: number;
}

const n = (v: unknown): number => {
  const x = Number(v);
  return Number.isFinite(x) ? x : 0;
};

export function computeTotals(
  items: TotalsItem[],
  taxes: TotalsTax[],
  discount: TotalsDiscount,
): DocTotals {
  const netTotal = items.reduce((s, i) => s + n(i.qty) * n(i.rate), 0);
  const totalQty = items.reduce((s, i) => s + n(i.qty), 0);
  const applyOn = discount.apply_discount_on || "Grand Total";

  // Discount applied on the Net Total reduces the taxable base before taxes.
  let discountAmount = 0;
  let taxableNet = netTotal;
  if (applyOn === "Net Total") {
    discountAmount =
      n(discount.discount_amount) > 0
        ? n(discount.discount_amount)
        : (n(discount.additional_discount_percentage) / 100) * netTotal;
    taxableNet = netTotal - discountAmount;
  }

  const taxAmounts: number[] = [];
  let running = taxableNet;
  taxes.forEach((t, idx) => {
    const rate = n(t.rate);
    let amt = 0;
    switch (t.charge_type) {
      case "Actual":
        amt = n(t.tax_amount);
        break;
      case "On Net Total":
        amt = (rate / 100) * taxableNet;
        break;
      case "On Previous Row Total":
        amt = (rate / 100) * running;
        break;
      case "On Previous Row Amount": {
        // row_id is 1-based and must reference a PRIOR row; otherwise contribute 0
        const rid = n(t.row_id);
        amt = rid >= 1 && rid <= idx ? (rate / 100) * (taxAmounts[rid - 1] ?? 0) : 0;
        break;
      }
      case "On Item Quantity":
        amt = rate * totalQty;
        break;
      default:
        amt = (rate / 100) * taxableNet;
    }
    taxAmounts.push(amt);
    running += amt;
  });
  const totalTaxes = taxAmounts.reduce((s, a) => s + a, 0);

  let grandTotal = taxableNet + totalTaxes;
  if (applyOn !== "Net Total") {
    discountAmount =
      n(discount.discount_amount) > 0
        ? n(discount.discount_amount)
        : (n(discount.additional_discount_percentage) / 100) * grandTotal;
    grandTotal -= discountAmount;
  }

  const roundedTotal = Math.round(grandTotal);
  return {
    totalQty,
    netTotal,
    totalTaxes,
    discountAmount,
    grandTotal,
    roundedTotal,
    roundingAdjustment: roundedTotal - grandTotal,
  };
}

// --- Indian-system number to words (for the In Words line) --------------------
const ONES = [
  "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
  "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen",
];
const TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"];

function twoDigits(num: number): string {
  if (num < 20) return ONES[num];
  return (TENS[Math.floor(num / 10)] + (num % 10 ? " " + ONES[num % 10] : "")).trim();
}
function threeDigits(num: number): string {
  const h = Math.floor(num / 100);
  const rest = num % 100;
  return [h ? `${ONES[h]} Hundred` : "", rest ? twoDigits(rest) : ""].filter(Boolean).join(" ");
}

function indianWords(value: number): string {
  if (value === 0) return "Zero";
  let num = value;
  const parts: string[] = [];
  const kharab = Math.floor(num / 1000000000000);
  num %= 1000000000000;
  const arab = Math.floor(num / 10000000000);
  num %= 10000000000;
  const crore = Math.floor(num / 10000000);
  num %= 10000000;
  const lakh = Math.floor(num / 100000);
  num %= 100000;
  const thousand = Math.floor(num / 1000);
  num %= 1000;
  if (kharab) parts.push(`${twoDigits(kharab)} Kharab`);
  if (arab) parts.push(`${twoDigits(arab)} Arab`);
  if (crore) parts.push(`${twoDigits(crore)} Crore`);
  if (lakh) parts.push(`${twoDigits(lakh)} Lakh`);
  if (thousand) parts.push(`${twoDigits(thousand)} Thousand`);
  if (num) parts.push(threeDigits(num));
  return parts.join(" ");
}

export function amountInWords(amount: number, currency = "INR"): string {
  const num = Math.floor(Math.abs(amount));
  const sign = amount < 0 ? "Minus " : "";
  return `${currency} ${sign}${indianWords(num)} Only`;
}
