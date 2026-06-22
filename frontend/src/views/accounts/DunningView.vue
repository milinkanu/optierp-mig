<script setup lang="ts">
// Dunning: overdue payment reminders. Pick a customer → see overdue invoices + interest
// + the auto-selected escalation tier → download PDF / email; plus a bulk "remind everyone".
import { onMounted, ref } from "vue";
import { api, openPdf } from "@/api/client";
import { useAccountsStore } from "@/stores/accounts";
import { useCompanyCurrency } from "@/composables/useCompanyCurrency";
import { formatCurrency, formatDate, formatNumber } from "@/utils/format";
import type { ErrorEnvelope } from "@/types/core";

interface DunningInvoice {
  voucher_no: string;
  posting_date: string;
  due_date: string | null;
  age_days: number;
  outstanding_amount: string;
  interest: string;
}
interface DunningNotice {
  party_name: string;
  party_email: string | null;
  as_of: string;
  dunning_type: string | null;
  letter_intro: string | null;
  invoices: DunningInvoice[];
  total_overdue: string;
  total_interest: string;
  dunning_fee: string;
  total_due: string;
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
const asOf = ref(today);

const notice = ref<DunningNotice | null>(null);
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
    notice.value = (
      await api.get<DunningNotice>(`/reports/dunning/${customerId.value}`, {
        params: { as_of: asOf.value },
      })
    ).data;
  } catch (e) {
    error.value = e as ErrorEnvelope;
    notice.value = null;
  } finally {
    loading.value = false;
  }
}

async function downloadPdf(): Promise<void> {
  if (!customerId.value) return;
  await openPdf(`/reports/dunning/${customerId.value}/print?as_of=${asOf.value}&format=pdf`);
}

async function emailOne(): Promise<void> {
  if (!customerId.value) return;
  emailing.value = true;
  emailResult.value = null;
  try {
    const payload: Record<string, unknown> = { customer_id: customerId.value, as_of: asOf.value };
    const recipients = emailTo.value.split(",").map((s) => s.trim()).filter(Boolean);
    if (recipients.length) payload.to = recipients;
    const resp = await api.post<{ status: string; to: string[]; error: string | null }>(
      "/reports/dunning/email",
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
      await api.post<BatchRow[]>("/reports/dunning/email-batch", { as_of: asOf.value })
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
    <h1 class="mb-1 text-xl font-semibold text-gray-900">Dunning — Overdue Reminders</h1>
    <p class="mb-4 text-sm text-gray-500">
      Chase overdue invoices: each reminder lists the late invoices, applies interest and the right
      escalation tier (set up under <router-link to="/m/dunning-type" class="text-primary underline">Dunning
      Type</router-link>), and can be emailed to one customer or everyone overdue at once.
    </p>

    <div class="mb-4 flex flex-wrap items-end gap-3 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div>
        <label class="form-label">Customer</label>
        <select v-model="customerId" class="form-input w-64">
          <option value="" disabled>Select…</option>
          <option v-for="c in store.customers" :key="c.id" :value="c.id">{{ c.customer_name }}</option>
        </select>
      </div>
      <div><label class="form-label">As of</label><input v-model="asOf" type="date" class="form-input" /></div>
      <button class="btn-primary" :disabled="loading || !customerId" @click="view">View</button>
      <button class="btn-secondary" :disabled="!customerId" @click="downloadPdf">Download PDF</button>
      <p v-if="error" class="text-sm text-red-600">{{ error.detail }}</p>
    </div>

    <div v-if="notice">
      <div v-if="!notice.invoices.length" class="rounded-lg border border-gray-200 bg-white p-6 text-center text-sm text-gray-400 shadow-sm">
        {{ notice.party_name }} has no overdue invoices as of {{ formatDate(notice.as_of) }}. 🎉
      </div>
      <template v-else>
        <div class="mb-4 flex flex-wrap items-end justify-between gap-3 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <div>
            <div class="text-sm font-semibold text-gray-900">{{ notice.party_name }}</div>
            <div class="text-xs text-gray-500">{{ notice.party_email || "No email on file" }}</div>
            <div v-if="notice.dunning_type" class="mt-1 inline-block rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
              {{ notice.dunning_type }}
            </div>
          </div>
          <div class="text-sm">Amount now due: <strong>{{ formatCurrency(notice.total_due, companyCurrency) }}</strong></div>
          <div class="flex items-end gap-2">
            <input v-model="emailTo" type="text" class="form-input w-56" placeholder="Recipient (blank = saved email)" />
            <button class="btn-primary" :disabled="emailing" @click="emailOne">{{ emailing ? "Sending…" : "Email" }}</button>
          </div>
        </div>
        <p v-if="emailResult" class="mb-3 text-sm" :class="emailResult.ok ? 'text-green-600' : 'text-red-600'">
          {{ emailResult.msg }}
        </p>

        <div class="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
          <table class="min-w-full text-sm">
            <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
              <tr>
                <th class="px-4 py-2">Invoice</th><th class="px-4 py-2">Due</th>
                <th class="px-4 py-2 text-right">Days Overdue</th>
                <th class="px-4 py-2 text-right">Outstanding</th><th class="px-4 py-2 text-right">Interest</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="inv in notice.invoices" :key="inv.voucher_no" class="border-t border-gray-100">
                <td class="px-4 py-1.5">{{ inv.voucher_no }}</td>
                <td class="px-4 py-1.5">{{ formatDate(inv.due_date ?? inv.posting_date) }}</td>
                <td class="px-4 py-1.5 text-right">{{ inv.age_days }}</td>
                <td class="px-4 py-1.5 text-right">{{ formatNumber(inv.outstanding_amount) }}</td>
                <td class="px-4 py-1.5 text-right">{{ Number(inv.interest) ? formatNumber(inv.interest) : "—" }}</td>
              </tr>
              <tr class="border-t-2 border-gray-300 bg-gray-50 font-semibold">
                <td class="px-4 py-2" colspan="3">Total now due (incl. interest{{ Number(notice.dunning_fee) ? " + fee" : "" }})</td>
                <td class="px-4 py-2 text-right">{{ formatNumber(notice.total_overdue) }}</td>
                <td class="px-4 py-2 text-right">{{ formatNumber(notice.total_due) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>

    <div class="mt-6 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <h2 class="text-sm font-semibold text-gray-900">Bulk reminders</h2>
      <p class="mb-3 text-xs text-gray-500">
        Emails a reminder (as of the date above) to every customer with an overdue invoice. Customers
        without overdue invoices or without an email on file are skipped.
      </p>
      <button class="btn-primary" :disabled="batchRunning" @click="emailBatch">
        {{ batchRunning ? "Sending…" : "Email all overdue customers" }}
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
              <td colspan="3" class="px-4 py-8 text-center text-gray-400">No customers with overdue invoices.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
