// Display formatting shared by every module view.
// Currency strings follow the invoice/company currency (INR gets the
// en-IN lakh/crore grouping users expect: ₹ 2,29,000.00).

const LOCALE_BY_CURRENCY: Record<string, string> = {
  INR: "en-IN",
  USD: "en-US",
  GBP: "en-GB",
  AED: "en-AE",
  EUR: "de-DE",
};

const formatterCache = new Map<string, Intl.NumberFormat>();

export function formatCurrency(value: string | number | null | undefined, currency = "INR"): string {
  const amount = Number(value ?? 0);
  if (Number.isNaN(amount)) return String(value ?? "");
  const key = currency;
  let formatter = formatterCache.get(key);
  if (!formatter) {
    try {
      formatter = new Intl.NumberFormat(LOCALE_BY_CURRENCY[currency] ?? undefined, {
        style: "currency",
        currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    } catch {
      formatter = new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    formatterCache.set(key, formatter);
  }
  return formatter.format(amount);
}

export function formatNumber(value: string | number | null | undefined, decimals = 2): string {
  const amount = Number(value ?? 0);
  if (Number.isNaN(amount)) return String(value ?? "");
  return amount.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function formatQty(value: string | number | null | undefined): string {
  const qty = Number(value ?? 0);
  if (Number.isNaN(qty)) return String(value ?? "");
  return qty % 1 === 0 ? String(qty) : qty.toFixed(2);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const [year, month, day] = value.slice(0, 10).split("-");
  if (!year || !month || !day) return value;
  return `${day}-${month}-${year}`;
}
