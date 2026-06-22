<script setup lang="ts">
// Statement of Accounts: per-customer ledger statement → view, download PDF, email;
// plus a bulk "email every customer with an outstanding balance" action.
import { onMounted, ref } from "vue";
import { api, openPdf } from "@/api/client";
import { useAccountsStore } from "@/stores/accounts";
import { useCompanyCurrency } from "@/composables/useCompanyCurrency";
import { formatCurrency, formatDate, formatNumber } from "@/utils/format";
import type { ErrorEnvelope } from "@/types/core";

interface StatementLine {
  posting_date: string;
  voucher_type: string;
  voucher_no: string;
  remarks: string | null;
  debit: string;
  credit: string;
  balance: string;
}
interface StatementOfAccounts {
  party_name: string;
  party_email: string | null;
  from_date: string;
  to_date: string;
  opening_balance: string;
  lines: StatementLine[];
  total_debit: string;
  total_credit: string;
  closing_balance: string;
  aging_0_30: string;
  aging_31_60: string;
  aging_61_90: string;
  aging_90_plus: string;
  aging_total: string;
}
interface BatchRow {
  party_id: string;
  party_name: string;
  status: string;
  detail: string | null;
}

const store = useAccountsStore();
const companyCurrency = useCompanyCurrency();

const today = new Date().toISOString().slice(0, 10);
const customerId = ref("");
const fromDate = ref(`${new Date().getFullYear()}-01-01`);
const toDate = ref(today);

const statement = ref<StatementOfAccounts | null>(null);
const loading = ref(false);
const error = ref<ErrorEnvelope | null>(null);

const emailTo = ref("");
const emailing = ref(false);
const emailResult = ref<{ ok: boolean; msg: string } | null>(null);

const batchRunning = ref(false);
const batchResults = ref<BatchRow[] | null>(null);

onMounted(() => {
  void store.fetchCustomers();
});

async function view(): Promise<void> {
  if (!customerId.value) return;
  loading.value = true;
  error.value = null;
  emailResult.value = null;
  try {
    statement.value = (
      await api.get<StatementOfAccounts>(`/reports/statement-of-accounts/${customerId.value}`, {
        params: { from_date: fromDate.value, to_date: toDate.value },
      })
    ).data;
  } catch (e) {
    error.value = e as ErrorEnvelope;
    statement.value = null;
  } finally {
    loading.value = false;
  }
}

async function downloadPdf(): Promise<void> {
  if (!customerId.value) return;
  await openPdf(
    `/reports/statement-of-accounts/${customerId.value}/print` +
      `?from_date=${fromDate.value}&to_date=${toDate.value}&format=pdf`,
  );
}

async function emailOne(): Promise<void> {
  if (!customerId.value) return;
  emailing.value = true;
  emailResult.value = null;
  try {
    const payload: Record<string, unknown> = {
      customer_id: customerId.value,
      from_date: fromDate.value,
      to_date: toDate.value,
    };
    const recipients = emailTo.value.split(",").map((s) => s.trim()).filter(Boolean);
    if (recipients.length) payload.to = recipients;
    const resp = await api.post<{ status: string; to: string[]; error: string | null }>(
      "/reports/statement-of-accounts/email",
      payload,
    );
    emailResult.value =
      resp.data.status === "Sent"
        ? { ok: true, msg: `Sent to ${resp.data.to.join(", ")}` }
        : { ok: false, msg: resp.data.error || "Delivery failed." };
  } catch (e) {
    emailResult.value = { ok: false, msg: (e as ErrorEnvelope).detail || "Failed to send." };
  } finally {
    emailing.value = false;
  }
}

async function emailBatch(): Promise<void> {
  batchRunning.value = true;
  batchResults.value = null;
  error.value = null;
  try {
    batchResults.value = (
      await api.post<BatchRow[]>("/reports/statement-of-accounts/email-batch", {
        from_date: fromDate.value,
        to_date: toDate.value,
      })
    ).data;
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    batchRunning.value = false;
  }
}
</script>

<template>
  <div>
    <h1 class="mb-1 text-xl font-semibold text-gray-900">Statement of Accounts</h1>
    <p class="mb-4 text-sm text-gray-500">
      A customer's invoices and payments over a period, with a running balance — view it, download a
      PDF, or email it. Use the bulk action to chase everyone who owes you in one click.
    </p>

    <div class="mb-4 flex flex-wrap items-end gap-3 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div>
        <label class="form-label">Customer</label>
        <select v-model="customerId" class="form-input w-64">
          <option value="" disabled>Select…</option>
          <option v-for="c in store.customers" :key="c.id" :value="c.id">{{ c.customer_name }}</option>
        </select>
      </div>
      <div><label class="form-label">From</label><input v-model="fromDate" type="date" class="form-input" /></div>
      <div><label class="form-label">To</label><input v-model="toDate" type="date" class="form-input" /></div>
      <button class="btn-primary" :disabled="loading || !customerId" @click="view">View</button>
      <button class="btn-secondary" :disabled="!customerId" @click="downloadPdf">Download PDF</button>
      <p v-if="error" class="text-sm text-red-600">{{ error.detail }}</p>
    </div>

    <!-- statement -->
    <div v-if="statement">
      <div class="mb-4 flex flex-wrap items-end justify-between gap-3 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <div>
          <div class="text-sm font-semibold text-gray-900">{{ statement.party_name }}</div>
          <div class="text-xs text-gray-500">{{ statement.party_email || "No email on file" }}</div>
          <div class="mt-1 text-xs text-gray-500">
            {{ formatDate(statement.from_date) }} – {{ formatDate(statement.to_date) }}
          </div>
        </div>
        <div class="flex items-end gap-6 text-sm">
          <span>Opening: <strong>{{ formatCurrency(statement.opening_balance, companyCurrency) }}</strong></span>
          <span>Closing: <strong>{{ formatCurrency(statement.closing_balance, companyCurrency) }}</strong></span>
        </div>
        <div class="flex items-end gap-2">
          <input
            v-model="emailTo"
            type="text"
            class="form-input w-56"
            placeholder="Recipient (blank = saved email)"
          />
          <button class="btn-primary" :disabled="emailing" @click="emailOne">
            {{ emailing ? "Sending…" : "Email" }}
          </button>
        </div>
      </div>
      <p v-if="emailResult" class="mb-3 text-sm" :class="emailResult.ok ? 'text-green-600' : 'text-red-600'">
        {{ emailResult.msg }}
      </p>

      <div class="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
        <table class="min-w-full text-sm">
          <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th class="px-4 py-2">Date</th><th class="px-4 py-2">Voucher</th>
              <th class="px-4 py-2 text-right">Debit</th><th class="px-4 py-2 text-right">Credit</th>
              <th class="px-4 py-2 text-right">Balance</th>
            </tr>
          </thead>
          <tbody>
            <tr class="border-t border-gray-100 bg-gray-50">
              <td class="px-4 py-1.5 font-medium" colspan="4">Opening Balance</td>
              <td class="px-4 py-1.5 text-right font-medium">{{ formatNumber(statement.opening_balance) }}</td>
            </tr>
            <tr v-for="(line, i) in statement.lines" :key="i" class="border-t border-gray-100">
              <td class="px-4 py-1.5 text-gray-500">{{ formatDate(line.posting_date) }}</td>
              <td class="px-4 py-1.5">
                <span class="text-gray-500">{{ line.voucher_type }}</span> {{ line.voucher_no }}
              </td>
              <td class="px-4 py-1.5 text-right">{{ Number(line.debit) ? formatNumber(line.debit) : "" }}</td>
              <td class="px-4 py-1.5 text-right">{{ Number(line.credit) ? formatNumber(line.credit) : "" }}</td>
              <td class="px-4 py-1.5 text-right">{{ formatNumber(line.balance) }}</td>
            </tr>
            <tr class="border-t-2 border-gray-300 bg-gray-50 font-semibold">
              <td class="px-4 py-2" colspan="2">Closing Balance</td>
              <td class="px-4 py-2 text-right">{{ formatNumber(statement.total_debit) }}</td>
              <td class="px-4 py-2 text-right">{{ formatNumber(statement.total_credit) }}</td>
              <td class="px-4 py-2 text-right">{{ formatNumber(statement.closing_balance) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="Number(statement.aging_total)" class="mt-3 rounded-lg border border-gray-200 bg-white p-4 text-sm shadow-sm">
        <span class="text-xs font-semibold uppercase tracking-wide text-gray-400">Outstanding by age</span>
        <div class="mt-1 flex flex-wrap gap-6">
          <span>0–30: <strong>{{ formatNumber(statement.aging_0_30) }}</strong></span>
          <span>31–60: <strong>{{ formatNumber(statement.aging_31_60) }}</strong></span>
          <span>61–90: <strong>{{ formatNumber(statement.aging_61_90) }}</strong></span>
          <span>90+: <strong>{{ formatNumber(statement.aging_90_plus) }}</strong></span>
          <span>Total due: <strong>{{ formatNumber(statement.aging_total) }}</strong></span>
        </div>
      </div>
    </div>

    <!-- bulk -->
    <div class="mt-6 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <h2 class="text-sm font-semibold text-gray-900">Bulk email</h2>
      <p class="mb-3 text-xs text-gray-500">
        Emails a statement (for the dates above) to every customer with an outstanding balance.
        Customers without an email on file are skipped.
      </p>
      <button class="btn-primary" :disabled="batchRunning" @click="emailBatch">
        {{ batchRunning ? "Sending…" : "Email all customers with a balance" }}
      </button>
      <div v-if="batchResults" class="mt-3 overflow-hidden rounded-lg border border-gray-200">
        <table class="min-w-full text-sm">
          <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr><th class="px-4 py-2">Customer</th><th class="px-4 py-2">Status</th><th class="px-4 py-2">Detail</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in batchResults" :key="r.party_id" class="border-t border-gray-100">
              <td class="px-4 py-1.5">{{ r.party_name }}</td>
              <td class="px-4 py-1.5"
                  :class="r.status === 'Sent' ? 'text-green-600' : r.status === 'Failed' ? 'text-red-600' : 'text-gray-500'">
                {{ r.status }}
              </td>
              <td class="px-4 py-1.5 text-gray-500">{{ r.detail ?? "—" }}</td>
            </tr>
            <tr v-if="!batchResults.length">
              <td colspan="3" class="px-4 py-8 text-center text-gray-400">No customers with an outstanding balance.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
