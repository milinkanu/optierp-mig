<script setup lang="ts">
// Bank Reconciliation tool: import bank-statement lines for a bank account, then
// match each line to an existing uncleared Payment Entry / Journal Entry. Matching
// sets that voucher's clearance_date, so the bank-rec statement (and balance_per_bank)
// converges. Posts no GL of its own. MVP = one line ↔ one voucher.

import { computed, onMounted, ref } from "vue";
import { api } from "@/api/client";
import { formatCurrency, formatDate } from "@/utils/format";
import { useCompanyCurrency } from "@/composables/useCompanyCurrency";
import { useAccountsStore } from "@/stores/accounts";
import type { ErrorEnvelope } from "@/types/core";

interface BankAccountItem {
  id: string;
  account_name: string;
  gl_account_id: string | null;
}
interface BankTxn {
  id: string;
  name: string;
  date: string;
  description: string | null;
  reference_number: string | null;
  deposit: string;
  withdrawal: string;
  status: string;
  matched_voucher_type: string | null;
  matched_voucher_id: string | null;
  matched_voucher_no: string | null;
  created_voucher: boolean;
}
interface Suggestion {
  voucher_type: string;
  voucher_id: string;
  voucher_no: string;
  posting_date: string;
  reference_no: string | null;
  amount: string;
}
interface InvoiceSuggestion {
  invoice_type: string; // Sales Invoice | Purchase Invoice
  invoice_id: string;
  name: string;
  party_name: string | null;
  posting_date: string;
  grand_total: string;
  outstanding_amount: string;
}
interface Summary {
  bank_account_id: string;
  gl_account_id: string | null;
  total: number;
  reconciled: number;
  unreconciled: number;
  unreconciled_amount: string;
  balance_per_books: string;
  balance_per_bank: string;
}
interface StagedRow {
  date: string;
  description: string;
  reference_number: string;
  deposit: number;
  withdrawal: number;
}

const companyCurrency = useCompanyCurrency();
const accountsStore = useAccountsStore();
const money = (v: string | number | null | undefined): string => formatCurrency(v, companyCurrency.value);
const today = new Date().toISOString().slice(0, 10);

const bankAccounts = ref<BankAccountItem[]>([]);
const bankAccountId = ref("");
const summary = ref<Summary | null>(null);
const transactions = ref<BankTxn[]>([]);
const statusFilter = ref<"" | "Unreconciled" | "Reconciled">("");

const error = ref<ErrorEnvelope | null>(null);
const notice = ref<string | null>(null);
const loading = ref(false);

const selectedAccount = computed(() => bankAccounts.value.find((b) => b.id === bankAccountId.value));
const noLedger = computed(() => !!selectedAccount.value && !selectedAccount.value.gl_account_id);

// --- staging grid (manual rows + CSV) --------------------------------------
const staged = ref<StagedRow[]>([]);
const fileInput = ref<HTMLInputElement | null>(null);

function blankRow(): StagedRow {
  return { date: today, description: "", reference_number: "", deposit: 0, withdrawal: 0 };
}
function addRow(): void {
  staged.value.push(blankRow());
}
function removeRow(i: number): void {
  staged.value.splice(i, 1);
}

function downloadTemplate(): void {
  const cols = ["date", "description", "reference_number", "deposit", "withdrawal"];
  const example = [`${today},NEFT from Globex Retail,UTR12345,10000,0`, `${today},Bank charges,CHG-09,0,177`];
  const csv = [cols.join(","), ...example].join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "bank-statement-template.csv";
  a.click();
  URL.revokeObjectURL(url);
}

// Minimal quote-aware CSV parser -> array of {header: value} objects.
function parseCSV(text: string): Array<Record<string, string>> {
  const records: string[][] = [];
  let field = "";
  let row: string[] = [];
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') inQuotes = false;
      else field += c;
    } else if (c === '"') {
      inQuotes = true;
    } else if (c === ",") {
      row.push(field); field = "";
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field); field = "";
      if (row.some((v) => v !== "")) records.push(row);
      row = [];
    } else {
      field += c;
    }
  }
  if (field !== "" || row.length) { row.push(field); if (row.some((v) => v !== "")) records.push(row); }
  if (records.length < 2) return [];
  const header = records[0].map((h) => h.trim().toLowerCase());
  return records.slice(1).map((r) => {
    const obj: Record<string, string> = {};
    header.forEach((h, idx) => (obj[h] = (r[idx] ?? "").trim()));
    return obj;
  });
}

async function onFileChange(e: Event): Promise<void> {
  error.value = null;
  notice.value = null;
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  try {
    const parsed = parseCSV(await file.text());
    const mapped: StagedRow[] = parsed
      .filter((o) => o.date && (Number(o.deposit) > 0 || Number(o.withdrawal) > 0))
      .map((o) => ({
        date: o.date,
        description: o.description || "",
        reference_number: o.reference_number || o.reference || "",
        deposit: Number(o.deposit) || 0,
        withdrawal: Number(o.withdrawal) || 0,
      }));
    if (!mapped.length) {
      error.value = { detail: "No valid rows (need date + deposit or withdrawal)." } as ErrorEnvelope;
      return;
    }
    staged.value = mapped;
  } catch {
    error.value = { detail: "Could not read that file as CSV." } as ErrorEnvelope;
  } finally {
    input.value = "";
  }
}

const stagedValid = computed(() =>
  staged.value.filter((r) => r.date && (Number(r.deposit) > 0 || Number(r.withdrawal) > 0)),
);

async function importStaged(): Promise<void> {
  if (!bankAccountId.value || !stagedValid.value.length) return;
  loading.value = true;
  error.value = null;
  notice.value = null;
  try {
    const payload = {
      bank_account_id: bankAccountId.value,
      transactions: stagedValid.value.map((r) => ({
        date: r.date,
        description: r.description || null,
        reference_number: r.reference_number || null,
        deposit: Number(r.deposit) || 0,
        withdrawal: Number(r.withdrawal) || 0,
      })),
    };
    const resp = await api.post<BankTxn[]>("/bank-transactions/import", payload);
    notice.value = `Imported ${resp.data.length} statement line(s).`;
    staged.value = [];
    await refresh();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    loading.value = false;
  }
}

// --- matching --------------------------------------------------------------
const openMatchId = ref(""); // txn currently showing suggestions
const suggestions = ref<Suggestion[]>([]);
const invoiceSuggestions = ref<InvoiceSuggestion[]>([]);
const loadingSuggestions = ref(false);
const voucherAccountId = ref(""); // contra account for "create voucher"
const voucherRemark = ref("");

function invoiceLink(inv: InvoiceSuggestion): string {
  return inv.invoice_type === "Sales Invoice"
    ? `/sales-invoices/${inv.invoice_id}`
    : `/purchase-invoices/${inv.invoice_id}`;
}

function voucherLink(voucherType: string | null, id: string): string {
  return voucherType === "Journal Entry" ? `/journal-entries/${id}` : `/payment-entries/${id}`;
}

async function findMatches(txn: BankTxn): Promise<void> {
  error.value = null;
  if (openMatchId.value === txn.id) {
    openMatchId.value = "";
    return;
  }
  openMatchId.value = txn.id;
  suggestions.value = [];
  invoiceSuggestions.value = [];
  voucherAccountId.value = "";
  voucherRemark.value = "";
  loadingSuggestions.value = true;
  try {
    const [vouchers, invoices] = await Promise.all([
      api.get<Suggestion[]>(`/bank-transactions/${txn.id}/match-suggestions`),
      api.get<InvoiceSuggestion[]>(`/bank-transactions/${txn.id}/invoice-suggestions`),
    ]);
    suggestions.value = vouchers.data;
    invoiceSuggestions.value = invoices.data;
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    loadingSuggestions.value = false;
  }
}

async function payInvoice(txn: BankTxn, inv: InvoiceSuggestion): Promise<void> {
  error.value = null;
  try {
    await api.post(`/bank-transactions/${txn.id}/pay-invoice`, {
      invoice_type: inv.invoice_type,
      invoice_id: inv.invoice_id,
    });
    openMatchId.value = "";
    await refresh();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

async function createVoucher(txn: BankTxn): Promise<void> {
  if (!voucherAccountId.value) return;
  error.value = null;
  try {
    await api.post(`/bank-transactions/${txn.id}/create-voucher`, {
      account_id: voucherAccountId.value,
      remarks: voucherRemark.value || null,
    });
    openMatchId.value = "";
    await refresh();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

async function match(txn: BankTxn, s: Suggestion): Promise<void> {
  error.value = null;
  try {
    await api.post(`/bank-transactions/${txn.id}/reconcile`, {
      voucher_type: s.voucher_type,
      voucher_id: s.voucher_id,
    });
    openMatchId.value = "";
    await refresh();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

async function unmatch(txn: BankTxn): Promise<void> {
  error.value = null;
  try {
    await api.post(`/bank-transactions/${txn.id}/unreconcile`, {});
    await refresh();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

async function remove(txn: BankTxn): Promise<void> {
  if (!confirm(`Delete statement line ${txn.name}?`)) return;
  error.value = null;
  try {
    await api.delete(`/bank-transactions/${txn.id}`);
    await refresh();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

// --- load ------------------------------------------------------------------
async function refresh(): Promise<void> {
  if (!bankAccountId.value) {
    transactions.value = [];
    summary.value = null;
    return;
  }
  loading.value = true;
  try {
    const params: Record<string, string> = { bank_account_id: bankAccountId.value };
    if (statusFilter.value) params.status = statusFilter.value;
    const [txns, sum] = await Promise.all([
      api.get<{ items: BankTxn[] }>("/bank-transactions", { params }),
      api.get<Summary>("/bank-transactions/summary", { params: { bank_account_id: bankAccountId.value } }),
    ]);
    transactions.value = txns.data.items ?? [];
    summary.value = sum.data;
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    loading.value = false;
  }
}

function onAccountChange(): void {
  openMatchId.value = "";
  staged.value = [];
  notice.value = null;
  void refresh();
}

onMounted(async () => {
  void accountsStore.fetchAccounts();
  try {
    const resp = await api.get<{ items: BankAccountItem[] }>("/registry/bank-account", {
      params: { page_size: 200 },
    });
    bankAccounts.value = resp.data.items ?? [];
    if (bankAccounts.value.length) {
      bankAccountId.value = bankAccounts.value[0].id;
      await refresh();
    }
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
});
</script>

<template>
  <div class="max-w-6xl">
    <div class="mb-4">
      <h1 class="text-xl font-semibold text-gray-900">Bank Reconciliation</h1>
      <p class="text-sm text-gray-500">
        Import your bank statement, then match each line to a payment/journal entry already in the
        books. Matching marks that voucher as <span class="font-medium">cleared</span> on the
        statement date, so your book balance and bank balance line up.
      </p>
    </div>

    <!-- Bank account picker -->
    <div class="mb-4 flex flex-wrap items-end gap-4">
      <div>
        <label class="form-label">Bank Account</label>
        <select v-model="bankAccountId" class="form-input w-64" @change="onAccountChange">
          <option v-if="!bankAccounts.length" value="">No bank accounts — create one first</option>
          <option v-for="b in bankAccounts" :key="b.id" :value="b.id">{{ b.account_name }}</option>
        </select>
      </div>
      <div>
        <label class="form-label">Show</label>
        <select v-model="statusFilter" class="form-input w-44" @change="refresh">
          <option value="">All lines</option>
          <option value="Unreconciled">Unreconciled</option>
          <option value="Reconciled">Reconciled</option>
        </select>
      </div>
      <p v-if="!bankAccounts.length" class="pb-2 text-sm text-amber-600">
        Create a Bank Account (Banking → Bank Account) with a Ledger Account set, then come back.
      </p>
    </div>

    <p v-if="noLedger" class="mb-3 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-700">
      This bank account has no <span class="font-medium">Ledger Account</span> set — open it under
      Bank Account and link it to its Chart-of-Accounts bank account before reconciling.
    </p>
    <p v-if="error" class="mb-3 text-sm text-red-600">{{ error.detail }}</p>
    <p v-if="notice" class="mb-3 rounded-md bg-green-50 px-3 py-2 text-sm text-green-700">{{ notice }}</p>

    <!-- Summary cards -->
    <div v-if="summary" class="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
      <div class="rounded-lg border border-gray-200 bg-white p-3 shadow-sm">
        <div class="text-xs uppercase text-gray-500">Reconciled</div>
        <div class="text-lg font-semibold">{{ summary.reconciled }} / {{ summary.total }}</div>
      </div>
      <div class="rounded-lg border border-gray-200 bg-white p-3 shadow-sm">
        <div class="text-xs uppercase text-gray-500">Unreconciled (net)</div>
        <div class="text-lg font-semibold">{{ money(summary.unreconciled_amount) }}</div>
        <div class="text-xs text-gray-400">{{ summary.unreconciled }} line(s)</div>
      </div>
      <div class="rounded-lg border border-gray-200 bg-white p-3 shadow-sm">
        <div class="text-xs uppercase text-gray-500">Balance per Books</div>
        <div class="text-lg font-semibold">{{ money(summary.balance_per_books) }}</div>
      </div>
      <div class="rounded-lg border border-gray-200 bg-white p-3 shadow-sm">
        <div class="text-xs uppercase text-gray-500">Balance per Bank</div>
        <div class="text-lg font-semibold">{{ money(summary.balance_per_bank) }}</div>
        <div class="text-xs text-gray-400">books minus uncleared</div>
      </div>
    </div>

    <!-- Import statement -->
    <div v-if="bankAccountId && !noLedger" class="mb-6 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div class="mb-2 flex items-center justify-between">
        <h2 class="text-sm font-semibold text-gray-900">Import statement lines</h2>
        <div class="flex gap-2">
          <button type="button" class="btn-secondary" @click="addRow">Add line</button>
          <button type="button" class="btn-secondary" @click="downloadTemplate">Template</button>
          <button type="button" class="btn-secondary" @click="fileInput?.click()">Upload CSV</button>
          <input ref="fileInput" type="file" accept=".csv,text/csv" class="hidden" @change="onFileChange" />
        </div>
      </div>
      <table v-if="staged.length" class="min-w-full text-sm">
        <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
          <tr>
            <th class="px-3 py-2">Date</th>
            <th class="px-3 py-2">Description</th>
            <th class="px-3 py-2">Reference</th>
            <th class="px-3 py-2 text-right">Deposit (in)</th>
            <th class="px-3 py-2 text-right">Withdrawal (out)</th>
            <th class="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in staged" :key="i" class="border-t border-gray-100">
            <td class="px-3 py-1.5"><input v-model="row.date" type="date" class="form-input py-1.5 w-40" /></td>
            <td class="px-3 py-1.5"><input v-model="row.description" class="form-input py-1.5 w-56" /></td>
            <td class="px-3 py-1.5"><input v-model="row.reference_number" class="form-input py-1.5 w-32" /></td>
            <td class="px-3 py-1.5"><input v-model.number="row.deposit" type="number" min="0" step="any" class="form-input py-1.5 w-32 text-right" /></td>
            <td class="px-3 py-1.5"><input v-model.number="row.withdrawal" type="number" min="0" step="any" class="form-input py-1.5 w-32 text-right" /></td>
            <td class="px-3 py-1.5"><button type="button" class="text-gray-400 hover:text-red-600" @click="removeRow(i)">✕</button></td>
          </tr>
        </tbody>
      </table>
      <p v-else class="py-3 text-sm text-gray-400">
        Add lines manually, or download the template and upload your bank's CSV
        (columns: date, description, reference_number, deposit, withdrawal).
      </p>
      <div v-if="staged.length" class="mt-3 flex justify-end">
        <button class="btn-primary" :disabled="loading || !stagedValid.length" @click="importStaged">
          {{ loading ? "Importing…" : `Import ${stagedValid.length} line(s)` }}
        </button>
      </div>
    </div>

    <!-- Statement lines -->
    <div v-if="bankAccountId" class="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
      <table class="min-w-full text-sm">
        <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
          <tr>
            <th class="px-3 py-2">Date</th>
            <th class="px-3 py-2">Description</th>
            <th class="px-3 py-2">Reference</th>
            <th class="px-3 py-2 text-right">Deposit</th>
            <th class="px-3 py-2 text-right">Withdrawal</th>
            <th class="px-3 py-2">Status</th>
            <th class="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="txn in transactions" :key="txn.id">
            <tr class="border-t border-gray-100">
              <td class="px-3 py-2 whitespace-nowrap">{{ formatDate(txn.date) }}</td>
              <td class="px-3 py-2">{{ txn.description || "—" }}</td>
              <td class="px-3 py-2 text-gray-500">{{ txn.reference_number || "—" }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ Number(txn.deposit) ? money(txn.deposit) : "" }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ Number(txn.withdrawal) ? money(txn.withdrawal) : "" }}</td>
              <td class="px-3 py-2">
                <span
                  class="rounded-full px-2 py-0.5 text-xs"
                  :class="txn.status === 'Reconciled' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'"
                >{{ txn.status }}</span>
                <router-link
                  v-if="txn.matched_voucher_id"
                  :to="voucherLink(txn.matched_voucher_type, txn.matched_voucher_id)"
                  class="ml-2 text-xs text-primary hover:underline"
                >{{ txn.matched_voucher_no }}</router-link>
              </td>
              <td class="px-3 py-2 text-right whitespace-nowrap">
                <template v-if="txn.status === 'Reconciled'">
                  <button class="text-xs text-gray-500 hover:text-red-600" @click="unmatch(txn)">Unmatch</button>
                </template>
                <template v-else>
                  <button class="text-xs font-medium text-primary hover:underline" @click="findMatches(txn)">
                    {{ openMatchId === txn.id ? "Hide" : "Find match" }}
                  </button>
                  <button class="ml-3 text-xs text-gray-400 hover:text-red-600" @click="remove(txn)">Delete</button>
                </template>
              </td>
            </tr>
            <!-- inline suggestions -->
            <tr v-if="openMatchId === txn.id" class="border-t border-gray-100 bg-gray-50">
              <td colspan="7" class="px-4 py-3">
                <div v-if="loadingSuggestions" class="text-sm text-gray-500">Looking for matches…</div>
                <template v-else>
                  <div v-if="suggestions.length">
                    <div class="mb-2 text-xs uppercase text-gray-500">Suggested matches (existing vouchers)</div>
                    <div
                      v-for="s in suggestions"
                      :key="s.voucher_id"
                      class="flex items-center justify-between border-b border-gray-100 py-1.5 last:border-0"
                    >
                      <div class="text-sm">
                        <router-link :to="voucherLink(s.voucher_type, s.voucher_id)" class="font-medium text-primary hover:underline">
                          {{ s.voucher_no }}
                        </router-link>
                        <span class="text-gray-400"> · {{ s.voucher_type }} · {{ formatDate(s.posting_date) }}</span>
                        <span v-if="s.reference_no" class="text-gray-400"> · {{ s.reference_no }}</span>
                        <span class="ml-2 tabular-nums text-gray-600">{{ money(s.amount) }}</span>
                      </div>
                      <button class="btn-primary px-3 py-1 text-xs" @click="match(txn, s)">Match</button>
                    </div>
                  </div>

                  <!-- settle an open invoice directly (auto-creates a Payment Entry) -->
                  <div v-if="invoiceSuggestions.length" class="mt-3 border-t border-gray-200 pt-3">
                    <div class="mb-2 text-xs uppercase text-gray-500">
                      Open {{ Number(txn.deposit) ? "sales" : "purchase" }} invoices to settle
                      <span class="normal-case text-gray-400">(creates &amp; clears a payment for you)</span>
                    </div>
                    <div
                      v-for="inv in invoiceSuggestions"
                      :key="inv.invoice_id"
                      class="flex items-center justify-between border-b border-gray-100 py-1.5 last:border-0"
                    >
                      <div class="text-sm">
                        <router-link :to="invoiceLink(inv)" class="font-medium text-primary hover:underline">
                          {{ inv.name }}
                        </router-link>
                        <span class="text-gray-400"> · {{ inv.party_name || inv.invoice_type }} · {{ formatDate(inv.posting_date) }}</span>
                        <span class="ml-2 tabular-nums text-gray-600">outstanding {{ money(inv.outstanding_amount) }}</span>
                      </div>
                      <button class="btn-primary px-3 py-1 text-xs" @click="payInvoice(txn, inv)">Pay &amp; match</button>
                    </div>
                  </div>

                  <p v-if="!suggestions.length && !invoiceSuggestions.length" class="text-sm text-gray-500">
                    No matching voucher or open invoice for this amount — record it directly:
                  </p>

                  <!-- create a journal entry from this line (charges / interest / etc.) -->
                  <div class="mt-3 border-t border-gray-200 pt-3">
                    <div class="mb-1 text-xs uppercase text-gray-500">
                      Or record as a journal entry
                      <span class="normal-case text-gray-400">
                        ({{ Number(txn.deposit) ? "credit" : "debit" }} this account
                        {{ money(Number(txn.deposit) || txn.withdrawal) }})
                      </span>
                    </div>
                    <div class="flex flex-wrap items-center gap-2">
                      <select v-model="voucherAccountId" class="form-input py-1.5 w-56">
                        <option value="">
                          {{ Number(txn.deposit) ? "Income / other account…" : "Expense / other account…" }}
                        </option>
                        <option v-for="a in accountsStore.accountOptions" :key="a.value" :value="a.value">
                          {{ a.label }}
                        </option>
                      </select>
                      <input v-model="voucherRemark" placeholder="Remark (optional)" class="form-input py-1.5 w-56" />
                      <button class="btn-primary px-3 py-1 text-xs" :disabled="!voucherAccountId" @click="createVoucher(txn)">
                        Create &amp; match
                      </button>
                    </div>
                  </div>
                </template>
              </td>
            </tr>
          </template>
          <tr v-if="!transactions.length">
            <td colspan="7" class="px-4 py-8 text-center text-sm text-gray-400">
              No statement lines yet — import your bank statement above.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
