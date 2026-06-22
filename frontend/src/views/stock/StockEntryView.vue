<script setup lang="ts">
// Stock Entry: list. Create/view via StockEntryFormView.

import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import DataTable, { type Column } from "@/components/shared/DataTable.vue";
import PaginationFooter from "@/components/shared/PaginationFooter.vue";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import { useList } from "@/composables/useList";
import { useCompanyCurrency } from "@/composables/useCompanyCurrency";
import { api } from "@/api/client";
import { formatCurrency, formatDate } from "@/utils/format";
import type { ErrorEnvelope } from "@/types/core";
import type { StockEntryListItem } from "@/types/stock";

const router = useRouter();
const companyCurrency = useCompanyCurrency();
const { items, total, page, pageSize, loading, fetchList, goToPage } =
  useList<StockEntryListItem>("/stock-entries");
const error = ref<ErrorEnvelope | null>(null);

const columns: Column[] = [
  { key: "name", label: "Entry" },
  { key: "posting_date", label: "Date" },
  { key: "purpose", label: "Purpose" },
  { key: "total_amount", label: "Amount", class: "text-right" },
  { key: "docstatus", label: "Status" },
];

function open(row: StockEntryListItem): void {
  router.push(`/stock-entries/${row.id}`);
}

async function rowAction(row: StockEntryListItem, action: "submit" | "cancel"): Promise<void> {
  error.value = null;
  try {
    await api.post(`/stock-entries/${row.id}/${action}`);
    await fetchList();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

onMounted(fetchList);
</script>

<template>
  <div>
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">Stock Entries</h1>
        <p class="text-sm text-gray-500">{{ total }} total</p>
      </div>
      <button class="btn-primary" @click="router.push('/stock-entries/new')">New Stock Entry</button>
    </div>
    <p v-if="error" class="mb-2 text-sm text-red-600">{{ error.detail }}</p>

    <DataTable :columns="columns" :rows="items" :loading="loading">
      <template #cell-name="{ row }">
        <button class="font-medium text-primary hover:underline" @click="open(row)">{{ row.name }}</button>
      </template>
      <template #cell-posting_date="{ value }">{{ formatDate(String(value)) }}</template>
      <template #cell-total_amount="{ value }">{{ formatCurrency(String(value), companyCurrency) }}</template>
      <template #cell-docstatus="{ value, row }">
        <div class="flex items-center gap-2">
          <StatusBadge :status="Number(value)" />
          <button v-if="value === 0" class="text-xs text-primary hover:underline" @click.stop="rowAction(row, 'submit')">submit</button>
          <button v-if="value === 1" class="text-xs text-red-600 hover:underline" @click.stop="rowAction(row, 'cancel')">cancel</button>
        </div>
      </template>
    </DataTable>
    <PaginationFooter :page="page" :page-size="pageSize" :total="total" @go-to="goToPage" />
  </div>
</template>
