// Module 02 — Accounts: TypeScript mirrors of the backend Pydantic schemas.

import type { DocumentMeta } from "./core";

export interface Customer extends DocumentMeta {
  customer_name: string;
  customer_type: string;
  tax_id: string | null;
  disabled: boolean;
}

export interface Supplier extends DocumentMeta {
  supplier_name: string;
  supplier_type: string;
  tax_id: string | null;
  disabled: boolean;
}

export interface InvoiceItemIn {
  item_code?: string | null;
  item_name: string;
  description?: string | null;
  qty: number;
  uom?: string | null;
  rate: number;
  account_id?: string | null;
}

export interface TaxRowIn {
  charge_type: string;
  rate: number;
  tax_amount?: number;
  row_id?: number | null;
  account_head_id: string;
  description?: string | null;
  add_deduct_tax?: string;
  category?: string;
}

export interface InvoiceListItem {
  id: string;
  name: string;
  posting_date: string;
  grand_total: string;
  outstanding_amount: string;
  status: string;
  docstatus: number;
}

export interface InvoiceDetail extends DocumentMeta {
  name: string;
  posting_date: string;
  due_date: string | null;
  currency: string;
  net_total: string;
  total_taxes_and_charges: string;
  discount_amount: string;
  grand_total: string;
  rounded_total: string;
  rounding_adjustment: string;
  outstanding_amount: string;
  status: string;
  is_return: boolean;
  remarks: string | null;
  items: Array<{
    idx: number;
    item_name: string;
    qty: string;
    rate: string;
    amount: string;
    net_amount: string;
  }>;
  taxes: Array<{
    idx: number;
    charge_type: string;
    rate: string;
    description: string | null;
    tax_amount: string;
    total: string;
  }>;
}

export interface SalesInvoiceDetail extends InvoiceDetail {
  customer_id: string;
}

export interface PurchaseInvoiceDetail extends InvoiceDetail {
  supplier_id: string;
  bill_no: string | null;
}

export interface JournalEntryRowIn {
  account_id: string;
  debit: number;
  credit: number;
  party_type?: string | null;
  party_id?: string | null;
  user_remark?: string | null;
}

export interface JournalEntryListItem {
  id: string;
  name: string;
  posting_date: string;
  voucher_type: string;
  total_debit: string;
  docstatus: number;
}

export interface PaymentEntryListItem {
  id: string;
  name: string;
  posting_date: string;
  payment_type: string;
  paid_amount: string;
  status: string;
  docstatus: number;
}

export interface TrialBalanceRow {
  account_id: string;
  account_name: string;
  root_type: string;
  is_group: boolean;
  path: string;
  opening_debit: string;
  opening_credit: string;
  debit: string;
  credit: string;
  closing_debit: string;
  closing_credit: string;
}

export interface StatementRow {
  account_id: string | null;
  account_name: string;
  root_type: string | null;
  is_group: boolean;
  indent: number;
  amount: string;
}

export interface AgingRow {
  party_name: string;
  voucher_no: string;
  posting_date: string;
  due_date: string | null;
  outstanding_amount: string;
  age_days: number;
  bucket_0_30: string;
  bucket_31_60: string;
  bucket_61_90: string;
  bucket_90_plus: string;
}

export interface FiscalYearInfo extends DocumentMeta {
  year: string;
  year_start_date: string;
  year_end_date: string;
}
