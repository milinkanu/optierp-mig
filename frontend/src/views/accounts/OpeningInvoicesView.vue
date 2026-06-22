<script setup lang="ts">
// Opening Invoice Creation Tool: bulk-enter outstanding receivables/payables at
// go-live. Each row becomes a submitted opening invoice booked to Temporary
// Opening (no income/expense, no tax) and shows up in AR/AP aging.
// Mirrors ERPNext's tool: per-row party / item / posting & due dates, plus
// "Create Missing Party" to find-or-create a customer/supplier by name.

import { computed, onMounted, ref } from "vue";
import { api } from "@/api/client";
import { useAccountsStore } from "@/stores/accounts";
import type { ErrorEnvelope } from "@/types/core";

interface Row {
  party_id: string;
  party_name: string;
  item_name: string;
  posting_date: string;
  due_date: string;
  outstanding_amount: number;
  bill_no: string;
}

const store = useAccountsStore();
const today = new Date().toISOString().slice(0, 10);

const kind = ref<"sales" | "purchase">("sales");
const defaultDate = ref(today);
const createMissing = ref(false);
const rows = ref<Row[]>([blankRow()]);

const error = ref<ErrorEnvelope | null>(null);
const saving = ref(false);
const result = ref<{ created: string[]; count: number } | null>(null);

function blankRow(): Row {
  return {
    party_id: "", party_name: "", item_name: "Opening Invoice",
    posting_date: defaultDate?.value ?? today, due_date: defaultDate?.value ?? today,
    outstanding_amount: 0, bill_no: "",
  };
}

const parties = computed(() => (kind.value === "sales" ? store.customers : store.suppliers));
const partyLabel = (p: { customer_name?: string; supplier_name?: string }): string =>
  p.customer_name ?? p.supplier_name ?? "";
const total = computed(() =>
  rows.value.reduce((s, r) => s + (Number(r.outstanding_amount) || 0), 0),
);

function addRow(): void {
  rows.value.push(blankRow());
}
function removeRow(i: number): void {
  rows.value.splice(i, 1);
}

// --- CSV download (template) / upload (populate the grid) --------------------
const fileInput = ref<HTMLInputElement | null>(null);

function csvColumns(): string[] {
  return kind.value === "purchase"
    ? ["party_name", "bill_no", "item_name", "posting_date", "due_date", "outstanding_amount"]
    : ["party_name", "item_name", "posting_date", "due_date", "outstanding_amount"];
}

function downloadTemplate(): void {
  const cols = csvColumns();
  const example: Record<string, string> = {
    party_name: kind.value === "sales" ? "Acme Home Stores" : "Initech Supplies",
    bill_no: "BILL-001",
    item_name: "Opening Invoice",
    posting_date: defaultDate.value,
    due_date: defaultDate.value,
    outstanding_amount: "10000",
  };
  const csv = [cols.join(","), cols.map((c) => example[c] ?? "").join(",")].join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `opening-${kind.value}-invoices-template.csv`;
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
  result.value = null;
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  try {
    const parsed = parseCSV(await file.text());
    const mapped: Row[] = parsed
      .filter((o) => (o.party_name || o.party_id) && Number(o.outstanding_amount) > 0)
      .map((o) => ({
        party_id: o.party_id || "",
        party_name: o.party_name || "",
        item_name: o.item_name || "Opening Invoice",
        posting_date: o.posting_date || defaultDate.value,
        due_date: o.due_date || o.posting_date || defaultDate.value,
        outstanding_amount: Number(o.outstanding_amount),
        bill_no: o.bill_no || "",
      }));
    if (!mapped.length) {
      error.value = { detail: "No valid rows found in the CSV (need party_name + outstanding_amount)." } as ErrorEnvelope;
      return;
    }
    rows.value = mapped;
    createMissing.value = true; // CSV gives names -> find-or-create on submit
  } catch {
    error.value = { detail: "Could not read that file as CSV." } as ErrorEnvelope;
  } finally {
    input.value = ""; // allow re-uploading the same file
  }
}

async function save(): Promise<void> {
  saving.value = true;
  error.value = null;
  result.value = null;
  try {
    const payload = {
      invoice_type: kind.value,
      posting_date: defaultDate.value,
      create_missing_party: createMissing.value,
      rows: rows.value
        .filter((r) => (r.party_id || r.party_name.trim()) && Number(r.outstanding_amount) > 0)
        .map((r) => ({
          ...(createMissing.value && !r.party_id
            ? { party_name: r.party_name.trim() }
            : { party_id: r.party_id }),
          item_name: r.item_name || "Opening Invoice",
          outstanding_amount: Number(r.outstanding_amount),
          posting_date: r.posting_date || defaultDate.value,
          due_date: r.due_date || r.posting_date || defaultDate.value,
          ...(kind.value === "purchase" && r.bill_no ? { bill_no: r.bill_no } : {}),
        })),
    };
    const resp = await api.post<{ created: string[]; count: number }>("/opening-invoices", payload);
    result.value = resp.data;
    rows.value = [blankRow()];
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  void store.fetchCustomers();
  void store.fetchSuppliers();
});
</script>

<template>
  <div class="max-w-5xl">
    <div class="mb-4">
      <h1 class="text-xl font-semibold text-gray-900">Opening Invoice Creation Tool</h1>
      <p class="text-sm text-gray-500">
        Load outstanding {{ kind === "sales" ? "customer receivables" : "supplier payables" }} from
        before go-live. Each row becomes a submitted invoice booked to <span class="font-medium">Temporary Opening</span>
        (no income/expense, no tax) and appears in {{ kind === "sales" ? "Accounts Receivable" : "Accounts Payable" }}.
      </p>
    </div>

    <div class="mb-4 flex flex-wrap items-end gap-6">
      <div>
        <label class="form-label">Invoice Type</label>
        <div class="inline-flex rounded-lg bg-gray-100 p-1 text-sm">
          <button
            v-for="k in (['sales', 'purchase'] as const)"
            :key="k"
            class="rounded-md px-3 py-1 capitalize"
            :class="kind === k ? 'bg-white text-primary shadow-sm' : 'text-gray-600'"
            @click="kind = k; result = null"
          >{{ k }}</button>
        </div>
      </div>
      <div>
        <label class="form-label">Default Posting Date</label>
        <input v-model="defaultDate" type="date" class="form-input w-44" />
      </div>
      <label class="flex items-center gap-2 pb-2 text-sm text-gray-700">
        <input v-model="createMissing" type="checkbox" />
        Create Missing Party
        <span class="text-xs text-gray-400">(create the {{ kind === "sales" ? "customer" : "supplier" }} from the name if it doesn't exist)</span>
      </label>
    </div>

    <p v-if="error" class="mb-3 text-sm text-red-600">{{ error.detail }}</p>
    <p v-if="result" class="mb-3 rounded-md bg-green-50 px-3 py-2 text-sm text-green-700">
      Created {{ result.count }} opening invoice(s): {{ result.created.join(", ") }}
    </p>

    <div class="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
      <table class="min-w-full text-sm">
        <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
          <tr>
            <th class="px-3 py-2 w-8">#</th>
            <th class="px-3 py-2">{{ kind === "sales" ? "Customer" : "Supplier" }}</th>
            <th v-if="kind === 'purchase'" class="px-3 py-2">Bill No.</th>
            <th class="px-3 py-2">Item Name</th>
            <th class="px-3 py-2">Posting Date</th>
            <th class="px-3 py-2">Due Date</th>
            <th class="px-3 py-2 text-right">Outstanding</th>
            <th class="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="i" class="border-t border-gray-100">
            <td class="px-3 py-1.5 text-gray-400">{{ i + 1 }}</td>
            <td class="px-3 py-1.5">
              <input
                v-if="createMissing"
                v-model="row.party_name"
                :placeholder="`${kind === 'sales' ? 'Customer' : 'Supplier'} name`"
                class="form-input py-1.5 w-48"
              />
              <select v-else v-model="row.party_id" class="form-input py-1.5 w-48">
                <option value="" disabled>{{ kind === "sales" ? "Customer" : "Supplier" }}…</option>
                <option v-for="p in parties" :key="p.id" :value="p.id">{{ partyLabel(p) }}</option>
              </select>
            </td>
            <td v-if="kind === 'purchase'" class="px-3 py-1.5">
              <input v-model="row.bill_no" placeholder="optional" class="form-input py-1.5 w-32" />
            </td>
            <td class="px-3 py-1.5"><input v-model="row.item_name" class="form-input py-1.5 w-40" /></td>
            <td class="px-3 py-1.5"><input v-model="row.posting_date" type="date" class="form-input py-1.5 w-40" /></td>
            <td class="px-3 py-1.5"><input v-model="row.due_date" type="date" class="form-input py-1.5 w-40" /></td>
            <td class="px-3 py-1.5">
              <input v-model.number="row.outstanding_amount" type="number" min="0" step="any" class="form-input py-1.5 w-32 text-right" />
            </td>
            <td class="px-3 py-1.5">
              <button type="button" class="text-gray-400 hover:text-red-600" @click="removeRow(i)">✕</button>
            </td>
          </tr>
        </tbody>
        <tfoot>
          <tr class="border-t border-gray-200 bg-gray-50">
            <td colspan="2" class="px-3 py-2">
              <div class="flex gap-2">
                <button type="button" class="btn-secondary" @click="addRow">Add Row</button>
                <button type="button" class="btn-secondary" @click="downloadTemplate">Download</button>
                <button type="button" class="btn-secondary" @click="fileInput?.click()">Upload CSV</button>
                <input ref="fileInput" type="file" accept=".csv,text/csv" class="hidden" @change="onFileChange" />
              </div>
            </td>
            <td :colspan="kind === 'purchase' ? 4 : 3" class="px-3 py-2 text-right font-medium text-gray-600">Total</td>
            <td class="px-3 py-2 text-right font-semibold">{{ total.toLocaleString() }}</td>
            <td></td>
          </tr>
        </tfoot>
      </table>
    </div>

    <div class="mt-4 flex justify-end">
      <button class="btn-primary" :disabled="saving || total <= 0" @click="save">
        {{ saving ? "Creating…" : "Create Opening Invoices" }}
      </button>
    </div>
  </div>
</template>
