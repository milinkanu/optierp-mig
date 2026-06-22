<script setup lang="ts">
// Read-only Payment Entry detail. Reachable from the Payment Entry list and the
// Bank Reconciliation tool. Shows the money flow + the invoices it settled, each
// linked back to the invoice (trace: bank line → payment → invoice).

import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client";
import { useAccountsStore } from "@/stores/accounts";
import { useCompanyCurrency } from "@/composables/useCompanyCurrency";
import { formatCurrency, formatDate } from "@/utils/format";
import type { ErrorEnvelope } from "@/types/core";
import type { PaymentEntryDetail } from "@/types/accounts";

const props = defineProps<{ id: string }>();
const router = useRouter();
const store = useAccountsStore();
const companyCurrency = useCompanyCurrency();
const money = (v: string | number | null | undefined): string => formatCurrency(v, companyCurrency.value);

const doc = ref<PaymentEntryDetail | null>(null);
const error = ref<ErrorEnvelope | null>(null);

const accountMap = computed<Record<string, string>>(() => {
  const m: Record<string, string> = {};
  for (const a of store.accountOptions) m[a.value] = a.label;
  return m;
});
const accountName = (id: string | null): string => (id ? accountMap.value[id] ?? "—" : "—");
const partyName = computed<string | null>(() => {
  if (!doc.value?.party_id) return null;
  const list = doc.value.party_type === "Customer" ? store.customers : store.suppliers;
  const p = list.find((x) => x.id === doc.value!.party_id) as
    | { customer_name?: string; supplier_name?: string }
    | undefined;
  return p?.customer_name ?? p?.supplier_name ?? null;
});

function invoiceLink(refDoctype: string, refId: string): string {
  return refDoctype === "Sales Invoice" ? `/sales-invoices/${refId}` : `/purchase-invoices/${refId}`;
}

onMounted(async () => {
  void store.fetchAccounts();
  void store.fetchCustomers();
  void store.fetchSuppliers();
  try {
    doc.value = (await api.get<PaymentEntryDetail>(`/payment-entries/${props.id}`)).data;
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
});
</script>

<template>
  <div class="mx-auto max-w-3xl">
    <button class="mb-3 text-sm text-gray-500 hover:text-gray-800" @click="router.back()">← Back</button>
    <p v-if="error" class="mb-3 text-sm text-red-600">{{ error.detail }}</p>

    <div v-if="doc">
      <div class="mb-4 flex items-start justify-between">
        <div>
          <h1 class="text-xl font-semibold text-gray-900">{{ doc.name }}</h1>
          <p class="text-sm text-gray-500">{{ doc.payment_type }} · {{ partyName || doc.party_type || "—" }}</p>
        </div>
        <span
          class="rounded-full px-2.5 py-1 text-xs"
          :class="doc.status === 'Cancelled' ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'"
        >{{ doc.status }}</span>
      </div>

      <div class="mb-4 grid grid-cols-2 gap-4 rounded-lg border border-gray-200 bg-white p-5 text-sm shadow-sm md:grid-cols-4">
        <div><div class="text-xs uppercase text-gray-500">Posting Date</div><div>{{ formatDate(doc.posting_date) }}</div></div>
        <div><div class="text-xs uppercase text-gray-500">Reference</div><div>{{ doc.reference_no || "—" }}</div></div>
        <div><div class="text-xs uppercase text-gray-500">Cleared On</div><div>{{ doc.clearance_date ? formatDate(doc.clearance_date) : "—" }}</div></div>
        <div><div class="text-xs uppercase text-gray-500">Amount</div><div class="font-semibold">{{ money(doc.paid_amount) }}</div></div>
      </div>

      <!-- money flow -->
      <div class="mb-4 rounded-lg border border-gray-200 bg-white p-5 text-sm shadow-sm">
        <h2 class="mb-2 text-sm font-semibold text-gray-900">Money flow</h2>
        <div class="flex items-center gap-3">
          <span class="rounded-md bg-gray-50 px-3 py-1.5">{{ accountName(doc.paid_from_id) }}</span>
          <span class="text-gray-400">→ {{ money(doc.paid_amount) }} →</span>
          <span class="rounded-md bg-gray-50 px-3 py-1.5">{{ accountName(doc.paid_to_id) }}</span>
        </div>
        <p v-if="Number(doc.unallocated_amount) > 0" class="mt-2 text-xs text-amber-600">
          {{ money(doc.unallocated_amount) }} is unallocated (on account).
        </p>
      </div>

      <!-- allocations -> invoices -->
      <div class="rounded-lg border border-gray-200 bg-white shadow-sm">
        <h2 class="border-b border-gray-100 px-5 py-3 text-sm font-semibold text-gray-900">
          Allocated to invoices
        </h2>
        <table class="min-w-full text-sm">
          <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th class="px-4 py-2">Invoice</th>
              <th class="px-4 py-2">Type</th>
              <th class="px-4 py-2 text-right">Invoice Total</th>
              <th class="px-4 py-2 text-right">Outstanding</th>
              <th class="px-4 py-2 text-right">Allocated</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in doc.references" :key="r.idx" class="border-t border-gray-100">
              <td class="px-4 py-2">
                <router-link :to="invoiceLink(r.reference_doctype, r.reference_id)" class="font-medium text-primary hover:underline">
                  {{ r.reference_name || "(open invoice)" }}
                </router-link>
              </td>
              <td class="px-4 py-2 text-gray-500">{{ r.reference_doctype }}</td>
              <td class="px-4 py-2 text-right tabular-nums">{{ money(r.total_amount) }}</td>
              <td class="px-4 py-2 text-right tabular-nums">{{ money(r.outstanding_amount) }}</td>
              <td class="px-4 py-2 text-right tabular-nums font-medium">{{ money(r.allocated_amount) }}</td>
            </tr>
            <tr v-if="!doc.references.length">
              <td colspan="5" class="px-4 py-6 text-center text-gray-400">
                On-account payment — not allocated to any invoice.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
