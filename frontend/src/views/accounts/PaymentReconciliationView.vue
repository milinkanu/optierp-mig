<script setup lang="ts">
// Payment Reconciliation tool: match a party's unallocated payments
// against their outstanding invoices (mirrors erpnext's tool).

import { computed, onMounted, ref, watch } from "vue";
import { useAccountsStore } from "@/stores/accounts";
import { api } from "@/api/client";
import type { ErrorEnvelope } from "@/types/core";
import type { UnreconciledResponse } from "@/types/accounts";

const store = useAccountsStore();

const partyType = ref<"Customer" | "Supplier">("Customer");
const partyId = ref("");
const data = ref<UnreconciledResponse | null>(null);
const paymentEntryId = ref("");
const allocations = ref<Record<string, number>>({}); // invoice_id -> amount
const error = ref<ErrorEnvelope | null>(null);
const loading = ref(false);
const saving = ref(false);
const successMessage = ref("");

const parties = computed(() => (partyType.value === "Customer" ? store.customers : store.suppliers));
const selectedPayment = computed(
  () => data.value?.payments.find((p) => p.payment_entry_id === paymentEntryId.value) ?? null,
);
const totalAllocated = computed(() =>
  Object.values(allocations.value).reduce((s, v) => s + (Number(v) || 0), 0),
);
const overAllocated = computed(
  () => selectedPayment.value !== null && totalAllocated.value > Number(selectedPayment.value.unallocated_amount),
);

async function fetchUnreconciled(): Promise<void> {
  data.value = null;
  paymentEntryId.value = "";
  allocations.value = {};
  successMessage.value = "";
  if (!partyId.value) return;
  loading.value = true;
  error.value = null;
  try {
    data.value = (
      await api.get<UnreconciledResponse>("/payment-reconciliation/unreconciled", {
        params: { party_type: partyType.value, party_id: partyId.value },
      })
    ).data;
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    loading.value = false;
  }
}

watch([partyType], () => {
  partyId.value = "";
  data.value = null;
});
watch([partyId], () => void fetchUnreconciled());

async function reconcile(): Promise<void> {
  if (!selectedPayment.value) return;
  saving.value = true;
  error.value = null;
  successMessage.value = "";
  try {
    const invoiceType = partyType.value === "Customer" ? "Sales Invoice" : "Purchase Invoice";
    const payload = {
      party_type: partyType.value,
      party_id: partyId.value,
      allocations: Object.entries(allocations.value)
        .filter(([, amount]) => Number(amount) > 0)
        .map(([invoiceId, amount]) => ({
          payment_entry_id: paymentEntryId.value,
          invoice_type: invoiceType,
          invoice_id: invoiceId,
          allocated_amount: Number(amount),
        })),
    };
    const resp = await api.post<{ allocations_applied: number }>(
      "/payment-reconciliation/reconcile",
      payload,
    );
    successMessage.value = `${resp.data.allocations_applied} allocation(s) applied.`;
    await fetchUnreconciled();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  await Promise.all([store.fetchCustomers(), store.fetchSuppliers()]);
});
</script>

<template>
  <div class="max-w-5xl">
    <h1 class="mb-4 text-xl font-semibold text-gray-900">Payment Reconciliation</h1>

    <div class="mb-4 flex items-end gap-3 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div>
        <label class="form-label">Party Type</label>
        <select v-model="partyType" class="form-input">
          <option>Customer</option>
          <option>Supplier</option>
        </select>
      </div>
      <div>
        <label class="form-label">{{ partyType }}</label>
        <select v-model="partyId" class="form-input w-64">
          <option value="" disabled>Select…</option>
          <option v-for="p in parties" :key="p.id" :value="p.id">
            {{ "customer_name" in p ? p.customer_name : p.supplier_name }}
          </option>
        </select>
      </div>
      <p v-if="error" class="text-sm text-red-600">{{ error.detail }}</p>
      <p v-if="successMessage" class="text-sm text-green-600">{{ successMessage }}</p>
    </div>

    <div v-if="data" class="grid grid-cols-2 gap-4">
      <!-- unallocated payments -->
      <div class="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <h2 class="mb-2 text-sm font-semibold text-gray-900">Unallocated Payments</h2>
        <label
          v-for="p in data.payments"
          :key="p.payment_entry_id"
          class="mb-1 flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm"
          :class="paymentEntryId === p.payment_entry_id ? 'bg-primary/10' : 'hover:bg-gray-50'"
        >
          <input v-model="paymentEntryId" type="radio" :value="p.payment_entry_id" />
          <span class="flex-1">{{ p.name }}</span>
          <span class="text-gray-500">{{ p.posting_date }}</span>
          <span class="font-medium">{{ p.unallocated_amount }}</span>
        </label>
        <p v-if="!data.payments.length" class="py-6 text-center text-sm text-gray-400">
          No unallocated payments for this party.
        </p>
      </div>

      <!-- outstanding invoices -->
      <div class="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <h2 class="mb-2 text-sm font-semibold text-gray-900">Outstanding Invoices</h2>
        <div
          v-for="invoice in data.invoices"
          :key="invoice.invoice_id"
          class="mb-1 grid grid-cols-12 items-center gap-2 text-sm"
        >
          <span class="col-span-4">{{ invoice.name }}</span>
          <span class="col-span-3 text-gray-500">{{ invoice.posting_date }}</span>
          <span class="col-span-2 text-right">{{ invoice.outstanding_amount }}</span>
          <input
            v-model.number="allocations[invoice.invoice_id]"
            type="number"
            min="0"
            step="any"
            :max="Number(invoice.outstanding_amount)"
            :disabled="!paymentEntryId"
            placeholder="Allocate"
            class="form-input col-span-3"
          />
        </div>
        <p v-if="!data.invoices.length" class="py-6 text-center text-sm text-gray-400">
          No outstanding invoices for this party.
        </p>
        <div v-if="data.invoices.length" class="mt-3 flex items-center justify-between border-t border-gray-100 pt-3">
          <p class="text-sm" :class="overAllocated ? 'text-red-600' : 'text-gray-600'">
            Allocating {{ totalAllocated.toFixed(2) }}
            <template v-if="selectedPayment"> of {{ selectedPayment.unallocated_amount }} available</template>
          </p>
          <button
            class="btn-primary"
            :disabled="saving || !paymentEntryId || totalAllocated <= 0 || overAllocated"
            @click="reconcile"
          >
            {{ saving ? "Reconciling…" : "Reconcile" }}
          </button>
        </div>
      </div>
    </div>
    <p v-else-if="loading" class="text-sm text-gray-500">Loading…</p>
  </div>
</template>
