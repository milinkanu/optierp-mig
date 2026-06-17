<script setup lang="ts">
// Shared list + detail view for Delivery Notes / Purchase Receipts.

import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import DataTable, { type Column } from "@/components/shared/DataTable.vue";
import PaginationFooter from "@/components/shared/PaginationFooter.vue";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import { useList } from "@/composables/useList";
import { useCompanyCurrency } from "@/composables/useCompanyCurrency";
import { api } from "@/api/client";
import { formatCurrency, formatDate, formatQty } from "@/utils/format";
import type { ErrorEnvelope } from "@/types/core";
import type { FulfilmentDetail, FulfilmentListItem } from "@/types/stock";

const props = defineProps<{ kind: "delivery-note" | "purchase-receipt"; id?: string }>();
const router = useRouter();
const companyCurrency = useCompanyCurrency();

const CONFIG = {
  "delivery-note": { endpoint: "/delivery-notes", title: "Delivery Notes", party: "Customer" },
  "purchase-receipt": { endpoint: "/purchase-receipts", title: "Purchase Receipts", party: "Supplier" },
} as const;

const cfg = computed(() => CONFIG[props.kind]);
const { items, total, page, pageSize, loading, filters, fetchList, goToPage, reset } =
  useList<FulfilmentListItem>(() => cfg.value.endpoint);

const statusFilter = ref("");
const doc = ref<FulfilmentDetail | null>(null);
const error = ref<ErrorEnvelope | null>(null);

const STATUSES = ["Draft", "To Bill", "Completed", "Cancelled"];

const columns = computed<Column[]>(() => [
  { key: "name", label: "Document" },
  { key: "party", label: cfg.value.party },
  { key: "posting_date", label: "Date" },
  { key: "grand_total", label: "Amount", class: "text-right" },
  { key: "per_billed", label: "Billed", class: "text-right" },
  { key: "status", label: "Status" },
]);

const docPartyName = computed(() => doc.value?.customer_name ?? doc.value?.supplier_name ?? "");

async function applyStatus(): Promise<void> {
  filters.value = statusFilter.value ? { status: statusFilter.value } : {};
  page.value = 1;
  await fetchList();
}

async function loadDoc(): Promise<void> {
  if (!props.id) {
    doc.value = null;
    return;
  }
  doc.value = (await api.get<FulfilmentDetail>(`${cfg.value.endpoint}/${props.id}`)).data;
}

async function action(name: "submit" | "cancel"): Promise<void> {
  if (!doc.value) return;
  error.value = null;
  try {
    doc.value = (await api.post<FulfilmentDetail>(`${cfg.value.endpoint}/${doc.value.id}/${name}`)).data;
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

function createInvoice(): void {
  if (!doc.value) return;
  if (props.kind === "delivery-note") {
    void router.push({ name: "sales-invoice-new", query: { delivery_note_id: doc.value.id } });
  } else {
    void router.push({ name: "purchase-invoice-new", query: { purchase_receipt_id: doc.value.id } });
  }
}

onMounted(async () => {
  if (props.id) await loadDoc();
  else await fetchList();
});

watch(
  () => props.id,
  async (id) => {
    if (id) {
      await loadDoc();
    } else {
      doc.value = null;
      await fetchList(); // back to a fresh (not stale/empty) list
    }
  },
);
watch(
  () => props.kind,
  async () => {
    statusFilter.value = "";
    if (!props.id) await reset();
  },
);
</script>

<template>
  <div>
    <!-- detail -->
    <div v-if="doc" class="max-w-5xl">
      <div class="mb-4 flex items-center justify-between">
        <div>
          <h1 class="text-xl font-semibold text-gray-900">{{ docPartyName || doc.name }}</h1>
          <p class="text-sm text-gray-500">{{ doc.name }}</p>
        </div>
        <div class="flex items-center gap-3">
          <StatusBadge :status="doc.status" />
          <button v-if="doc.docstatus === 0" class="btn-primary" @click="action('submit')">Submit</button>
          <button v-if="doc.docstatus === 1 && Number(doc.per_billed) < 99.999"
                  class="btn-primary" @click="createInvoice">Create Invoice</button>
          <button v-if="doc.docstatus === 1" class="btn-secondary" @click="action('cancel')">Cancel</button>
          <button class="btn-secondary" @click="router.push(cfg.endpoint)">Back to list</button>
        </div>
      </div>
      <p v-if="error" class="mb-3 text-sm text-red-600">{{ error.detail }}</p>

      <div class="mb-4 grid grid-cols-2 gap-x-8 gap-y-3 rounded-lg border border-gray-200 bg-white p-5 shadow-sm md:grid-cols-4">
        <div>
          <div class="text-xs font-semibold uppercase tracking-wide text-gray-400">{{ cfg.party }}</div>
          <div class="mt-0.5 text-sm font-medium text-gray-900">{{ docPartyName || "—" }}</div>
        </div>
        <div>
          <div class="text-xs font-semibold uppercase tracking-wide text-gray-400">Date</div>
          <div class="mt-0.5 text-sm text-gray-900">{{ formatDate(doc.posting_date) }}</div>
        </div>
        <div>
          <div class="text-xs font-semibold uppercase tracking-wide text-gray-400">Billed</div>
          <div class="mt-0.5 text-sm text-gray-900">{{ formatQty(doc.per_billed) }}%</div>
        </div>
        <div>
          <div class="text-xs font-semibold uppercase tracking-wide text-gray-400">Total</div>
          <div class="mt-0.5 text-sm font-medium text-gray-900">
            {{ formatCurrency(doc.grand_total, doc.currency ?? companyCurrency) }}
          </div>
        </div>
      </div>

      <div class="rounded-lg border border-gray-200 bg-white shadow-sm">
        <table class="min-w-full text-sm">
          <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th class="px-4 py-2">#</th><th class="px-4 py-2">Item</th>
              <th class="px-4 py-2 text-right">Qty</th>
              <th class="px-4 py-2 text-right">Billed Qty</th>
              <th class="px-4 py-2 text-right">Rate</th>
              <th class="px-4 py-2 text-right">Amount</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in doc.items" :key="item.idx" class="border-t border-gray-100">
              <td class="px-4 py-2">{{ item.idx }}</td>
              <td class="px-4 py-2 font-medium text-gray-900">
                {{ item.item_code ? `${item.item_code} — ` : "" }}{{ item.item_name }}
              </td>
              <td class="px-4 py-2 text-right">{{ formatQty(item.qty) }}</td>
              <td class="px-4 py-2 text-right">{{ formatQty(item.billed_qty) }}</td>
              <td class="px-4 py-2 text-right">{{ formatCurrency(item.rate, doc.currency ?? companyCurrency) }}</td>
              <td class="px-4 py-2 text-right">{{ formatCurrency(item.amount, doc.currency ?? companyCurrency) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- list -->
    <div v-else>
      <div class="mb-4 flex items-center justify-between">
        <div>
          <h1 class="text-xl font-semibold text-gray-900">{{ cfg.title }}</h1>
          <p class="text-sm text-gray-500">
            {{ total }} total · created from
            {{ kind === "delivery-note" ? "Sales Orders" : "Purchase Orders" }}
          </p>
        </div>
        <div class="flex items-center gap-3">
          <select v-model="statusFilter" class="form-input w-40" @change="applyStatus">
            <option value="">All statuses</option>
            <option v-for="s in STATUSES" :key="s" :value="s">{{ s }}</option>
          </select>
          <button class="btn-primary" @click="router.push(`${cfg.endpoint}/new`)">
            New {{ cfg.title.slice(0, -1) }}
          </button>
        </div>
      </div>
      <DataTable
        :columns="columns"
        :rows="items"
        :loading="loading"
        @row-click="(row) => router.push(`${cfg.endpoint}/${row.id}`)"
      >
        <template #cell-name="{ row }">
          <span class="font-medium text-gray-900">{{ row.name }}</span>
        </template>
        <template #cell-party="{ row }">
          {{ row.customer_name ?? row.supplier_name ?? "—" }}
        </template>
        <template #cell-posting_date="{ value }">
          {{ formatDate(String(value)) }}
        </template>
        <template #cell-grand_total="{ row }">
          {{ formatCurrency(row.grand_total, row.currency ?? companyCurrency) }}
        </template>
        <template #cell-per_billed="{ value }">
          {{ formatQty(String(value)) }}%
        </template>
        <template #cell-status="{ value }">
          <StatusBadge :status="String(value)" />
        </template>
      </DataTable>
      <PaginationFooter :page="page" :page-size="pageSize" :total="total" @go-to="goToPage" />
    </div>
  </div>
</template>
