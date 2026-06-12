<script setup lang="ts">
// Payment Entry list + creation (Receive/Pay with invoice allocation).

import { computed, onMounted, ref, watch } from "vue";
import DataTable, { type Column } from "@/components/shared/DataTable.vue";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import { useList } from "@/composables/useList";
import { useAccountsStore } from "@/stores/accounts";
import { api } from "@/api/client";
import type { ErrorEnvelope, ListResponse } from "@/types/core";
import type { InvoiceListItem, PaymentEntryListItem } from "@/types/accounts";

const store = useAccountsStore();
const { items, total, loading, fetchList } = useList<PaymentEntryListItem>("/payment-entries");

const showForm = ref(false);
const paymentType = ref<"Receive" | "Pay">("Receive");
const partyId = ref("");
const bankAccountId = ref("");
const postingDate = ref(new Date().toISOString().slice(0, 10));
const openInvoices = ref<InvoiceListItem[]>([]);
const allocations = ref<Record<string, number>>({});
const error = ref<ErrorEnvelope | null>(null);
const saving = ref(false);

const parties = computed(() => (paymentType.value === "Receive" ? store.customers : store.suppliers));
const invoiceEndpoint = computed(() =>
  paymentType.value === "Receive" ? "/sales-invoices" : "/purchase-invoices",
);
const refDoctype = computed(() =>
  paymentType.value === "Receive" ? "Sales Invoice" : "Purchase Invoice",
);
const bankAccounts = computed(() =>
  store.leafAccounts.filter((a) => a.account_type === "Bank" || a.account_type === "Cash"),
);
const totalAllocated = computed(() =>
  Object.values(allocations.value).reduce((s, v) => s + (Number(v) || 0), 0),
);

watch([partyId, paymentType], async () => {
  openInvoices.value = [];
  allocations.value = {};
  if (!partyId.value) return;
  // unpaid + partly paid + overdue invoices of the selected party
  const resp = await api.get<ListResponse<InvoiceListItem>>(invoiceEndpoint.value, {
    params: { page_size: 100 },
  });
  openInvoices.value = resp.data.items.filter(
    (i) => i.docstatus === 1 && Number(i.outstanding_amount) > 0,
  );
});

async function save(): Promise<void> {
  saving.value = true;
  error.value = null;
  try {
    const references = Object.entries(allocations.value)
      .filter(([, amount]) => Number(amount) > 0)
      .map(([referenceId, amount]) => ({
        reference_doctype: refDoctype.value,
        reference_id: referenceId,
        allocated_amount: Number(amount),
      }));
    const payload: Record<string, unknown> = {
      posting_date: postingDate.value,
      payment_type: paymentType.value,
      party_type: paymentType.value === "Receive" ? "Customer" : "Supplier",
      party_id: partyId.value,
      paid_amount: totalAllocated.value,
      references,
    };
    if (paymentType.value === "Receive") payload.paid_to_id = bankAccountId.value;
    else payload.paid_from_id = bankAccountId.value;

    const resp = await api.post("/payment-entries", payload);
    await api.post(`/payment-entries/${(resp.data as { id: string }).id}/submit`);
    showForm.value = false;
    allocations.value = {};
    await fetchList();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    saving.value = false;
  }
}

const columns: Column[] = [
  { key: "name", label: "Payment" },
  { key: "posting_date", label: "Date" },
  { key: "payment_type", label: "Type" },
  { key: "paid_amount", label: "Amount", class: "text-right" },
  { key: "status", label: "Status" },
];

onMounted(async () => {
  await Promise.all([fetchList(), store.fetchAccounts(), store.fetchCustomers(), store.fetchSuppliers()]);
});
</script>

<template>
  <div>
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">Payment Entries</h1>
        <p class="text-sm text-gray-500">{{ total }} total</p>
      </div>
      <button class="btn-primary" @click="showForm = !showForm">
        {{ showForm ? "Close" : "New Payment" }}
      </button>
    </div>

    <form v-if="showForm" class="mb-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm" @submit.prevent="save">
      <div class="grid grid-cols-4 gap-4">
        <div>
          <label class="form-label">Type</label>
          <select v-model="paymentType" class="form-input">
            <option>Receive</option>
            <option>Pay</option>
          </select>
        </div>
        <div>
          <label class="form-label">{{ paymentType === "Receive" ? "Customer" : "Supplier" }}*</label>
          <select v-model="partyId" required class="form-input">
            <option value="" disabled>Select…</option>
            <option v-for="p in parties" :key="p.id" :value="p.id">
              {{ "customer_name" in p ? p.customer_name : p.supplier_name }}
            </option>
          </select>
        </div>
        <div>
          <label class="form-label">Bank/Cash Account*</label>
          <select v-model="bankAccountId" required class="form-input">
            <option value="" disabled>Select…</option>
            <option v-for="a in bankAccounts" :key="a.id" :value="a.id">{{ a.account_name }}</option>
          </select>
        </div>
        <div>
          <label class="form-label">Posting Date*</label>
          <input v-model="postingDate" type="date" required class="form-input" />
        </div>
      </div>

      <div v-if="openInvoices.length" class="mt-4">
        <h2 class="mb-2 text-sm font-semibold text-gray-900">Allocate against open invoices</h2>
        <div
          v-for="invoice in openInvoices"
          :key="invoice.id"
          class="mb-1 grid grid-cols-12 items-center gap-2 text-sm"
        >
          <span class="col-span-4">{{ invoice.name }}</span>
          <span class="col-span-3 text-gray-500">{{ invoice.posting_date }}</span>
          <span class="col-span-2 text-right">{{ invoice.outstanding_amount }}</span>
          <input
            v-model.number="allocations[invoice.id]"
            type="number"
            min="0"
            step="any"
            :max="Number(invoice.outstanding_amount)"
            placeholder="Allocate"
            class="form-input col-span-3"
          />
        </div>
        <p class="mt-2 text-right text-sm font-medium">Total payment: {{ totalAllocated.toFixed(2) }}</p>
      </div>
      <p v-else-if="partyId" class="mt-4 text-sm text-gray-500">No open invoices for this party.</p>

      <p v-if="error" class="mt-2 text-sm text-red-600">{{ error.detail }}</p>
      <div class="mt-4 flex justify-end">
        <button type="submit" class="btn-primary" :disabled="saving || totalAllocated <= 0 || !bankAccountId">
          {{ saving ? "Posting…" : "Save & Submit" }}
        </button>
      </div>
    </form>

    <DataTable :columns="columns" :rows="items" :loading="loading">
      <template #cell-status="{ value }">
        <StatusBadge :status="String(value)" />
      </template>
    </DataTable>
  </div>
</template>
