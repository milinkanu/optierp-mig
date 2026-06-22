<script setup lang="ts">
// Payment Requests: create a "please pay ₹X" request, email it as a PDF, track status.
// Print/Send reuse the shared components (it's registered with the generic print endpoints).
import { onMounted, ref, watch } from "vue";
import { api } from "@/api/client";
import { useAccountsStore } from "@/stores/accounts";
import { useCompanyCurrency } from "@/composables/useCompanyCurrency";
import { formatCurrency, formatDate } from "@/utils/format";
import PrintButton from "@/components/shared/PrintButton.vue";
import SendEmailButton from "@/components/shared/SendEmailButton.vue";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import type { ErrorEnvelope, ListResponse } from "@/types/core";

interface PaymentRequestRow {
  id: string;
  name: string;
  customer_name: string | null;
  posting_date: string;
  amount: string;
  status: string;
}

interface OpenInvoice {
  id: string;
  name: string;
  outstanding_amount: string;
}

const store = useAccountsStore();
const companyCurrency = useCompanyCurrency();

const rows = ref<PaymentRequestRow[]>([]);
const loading = ref(false);
const error = ref<ErrorEnvelope | null>(null);

const showForm = ref(false);
const today = new Date().toISOString().slice(0, 10);
const fCustomer = ref("");
const fInvoice = ref("");
const fAmount = ref<number | null>(null);
const fDue = ref("");
const fMessage = ref("");
const saving = ref(false);
const openInvoices = ref<OpenInvoice[]>([]);

// When a customer is picked, load their unpaid invoices so the request can ask for
// exactly what's owed; selecting one fills the amount (still editable for partials).
async function loadOpenInvoices(customerId: string): Promise<void> {
  openInvoices.value = [];
  fInvoice.value = "";
  if (!customerId) return;
  try {
    const items = (
      await api.get<ListResponse<OpenInvoice>>("/sales-invoices", {
        params: { customer_id: customerId, page_size: 200 },
      })
    ).data.items;
    openInvoices.value = items.filter((i) => Number(i.outstanding_amount) > 0);
  } catch {
    openInvoices.value = [];
  }
}

watch(fCustomer, (id) => {
  fAmount.value = null;
  void loadOpenInvoices(id);
});
watch(fInvoice, (id) => {
  const inv = openInvoices.value.find((i) => i.id === id);
  if (inv) fAmount.value = Number(inv.outstanding_amount);
});

async function fetchList(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    rows.value = (
      await api.get<ListResponse<PaymentRequestRow>>("/payment-requests", { params: { page_size: 100 } })
    ).data.items;
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    loading.value = false;
  }
}

async function save(): Promise<void> {
  if (!fCustomer.value || !fAmount.value) return;
  saving.value = true;
  error.value = null;
  try {
    await api.post("/payment-requests", {
      customer_id: fCustomer.value,
      reference_invoice_id: fInvoice.value || null,
      posting_date: today,
      due_date: fDue.value || null,
      amount: fAmount.value,
      message: fMessage.value || null,
    });
    showForm.value = false;
    fCustomer.value = "";
    fInvoice.value = "";
    fAmount.value = null;
    fDue.value = "";
    fMessage.value = "";
    await fetchList();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    saving.value = false;
  }
}

async function setStatus(row: PaymentRequestRow, status: string): Promise<void> {
  try {
    await api.post(`/payment-requests/${row.id}/status`, null, { params: { status } });
    await fetchList();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

onMounted(async () => {
  await Promise.all([store.fetchCustomers(), fetchList()]);
});
</script>

<template>
  <div>
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">Payment Requests</h1>
        <p class="text-sm text-gray-500">
          Ask a customer to pay a specific amount, email it as a PDF (with your bank details), and track
          it to Paid. An online "Pay Now" link can be added later with a payment gateway.
        </p>
      </div>
      <button class="btn-primary" @click="showForm = !showForm">{{ showForm ? "Close" : "New Payment Request" }}</button>
    </div>

    <form v-if="showForm" class="mb-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm" @submit.prevent="save">
      <div class="grid grid-cols-2 gap-4 md:grid-cols-4">
        <div>
          <label class="form-label">Customer*</label>
          <select v-model="fCustomer" required class="form-input">
            <option value="" disabled>Select…</option>
            <option v-for="c in store.customers" :key="c.id" :value="c.id">{{ c.customer_name }}</option>
          </select>
        </div>
        <div>
          <label class="form-label">Against invoice</label>
          <select v-model="fInvoice" class="form-input" :disabled="!fCustomer">
            <option value="">— advance / custom amount —</option>
            <option v-for="inv in openInvoices" :key="inv.id" :value="inv.id">
              {{ inv.name }} — {{ formatCurrency(inv.outstanding_amount, companyCurrency) }} due
            </option>
          </select>
        </div>
        <div>
          <label class="form-label">Amount*</label>
          <input v-model.number="fAmount" type="number" min="0" step="any" required class="form-input" />
        </div>
        <div>
          <label class="form-label">Pay By</label>
          <input v-model="fDue" type="date" class="form-input" />
        </div>
        <div class="col-span-2 md:col-span-4">
          <label class="form-label">Message</label>
          <input v-model="fMessage" class="form-input" placeholder="Optional note to the customer" />
        </div>
      </div>
      <p class="mt-2 text-xs text-gray-500">
        Pick an unpaid invoice to request exactly what's due (the amount fills in automatically), or
        leave it on "advance / custom amount" to request a deposit before invoicing.
      </p>
      <p v-if="error" class="mt-2 text-sm text-red-600">{{ error.detail }}</p>
      <div class="mt-4 flex justify-end">
        <button type="submit" class="btn-primary" :disabled="saving || !fCustomer || !fAmount">
          {{ saving ? "Saving…" : "Create" }}
        </button>
      </div>
    </form>

    <div class="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      <table class="min-w-full text-sm">
        <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
          <tr>
            <th class="px-4 py-2">Request</th><th class="px-4 py-2">Customer</th>
            <th class="px-4 py-2">Date</th><th class="px-4 py-2 text-right">Amount</th>
            <th class="px-4 py-2">Status</th><th class="px-4 py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id" class="border-t border-gray-100">
            <td class="px-4 py-1.5 font-medium text-gray-900">{{ row.name }}</td>
            <td class="px-4 py-1.5">{{ row.customer_name ?? "—" }}</td>
            <td class="px-4 py-1.5 text-gray-500">{{ formatDate(row.posting_date) }}</td>
            <td class="px-4 py-1.5 text-right">{{ formatCurrency(row.amount, companyCurrency) }}</td>
            <td class="px-4 py-1.5"><StatusBadge :status="row.status" /></td>
            <td class="px-4 py-1.5">
              <div class="flex flex-wrap items-center gap-2">
                <PrintButton :path="`/print/Payment%20Request/${row.id}`" :title="`${row.name} — Preview`" />
                <SendEmailButton doctype="Payment Request" :doc-id="row.id" :doc-name="row.name" />
                <button v-if="row.status === 'Requested'" class="text-xs text-green-700 hover:underline"
                        @click="setStatus(row, 'Paid')">mark paid</button>
                <button v-if="row.status === 'Requested'" class="text-xs text-red-600 hover:underline"
                        @click="setStatus(row, 'Cancelled')">cancel</button>
              </div>
            </td>
          </tr>
          <tr v-if="!rows.length && !loading">
            <td colspan="6" class="px-4 py-8 text-center text-gray-400">
              No payment requests yet. Create one to ask a customer to pay.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
