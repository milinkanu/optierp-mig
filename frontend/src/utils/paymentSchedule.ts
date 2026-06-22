// Derive a payment-due breakdown from a Payment Terms Template's installments,
// a document total, and its posting date. No data is stored on the document —
// the schedule is always computed from (template + total + date), so it stays
// consistent. The last installment absorbs any rounding remainder so the rows
// sum exactly to the total.

export interface PaymentInstallment {
  description?: string | null;
  invoice_portion?: number | string | null;
  credit_days?: number | string | null;
}

export interface ScheduleRow {
  label: string;
  portion: number;
  dueDate: string; // YYYY-MM-DD
  amount: number;
}

const round2 = (n: number): number => Math.round(n * 100) / 100;

// Add whole days to a YYYY-MM-DD date, returning YYYY-MM-DD (UTC-safe).
function addDays(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return isoDate;
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function buildPaymentSchedule(
  installments: PaymentInstallment[],
  total: number,
  postingDate: string,
): ScheduleRow[] {
  const grand = Number(total) || 0;
  const rows: ScheduleRow[] = [];
  let allocated = 0;
  installments.forEach((inst, i) => {
    const portion = Number(inst.invoice_portion) || 0;
    const isLast = i === installments.length - 1;
    const amount = isLast ? round2(grand - allocated) : round2((grand * portion) / 100);
    allocated += amount;
    rows.push({
      label: inst.description?.trim() || `Installment ${i + 1}`,
      portion,
      dueDate: addDays(postingDate, Number(inst.credit_days) || 0),
      amount,
    });
  });
  return rows;
}

// Sum of installment portions — used to warn when a template doesn't total 100%.
export function totalPortion(installments: PaymentInstallment[]): number {
  return installments.reduce((s, i) => s + (Number(i.invoice_portion) || 0), 0);
}
