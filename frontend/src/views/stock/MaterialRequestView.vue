<script setup lang="ts">
// Material Request: list + create; "Order" jumps to a prefilled Purchase Order.

import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import DataTable, { type Column } from "@/components/shared/DataTable.vue";
import PaginationFooter from "@/components/shared/PaginationFooter.vue";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import { useList } from "@/composables/useList";
import { useStockStore } from "@/stores/stock";
import { api } from "@/api/client";
import { formatDate, formatQty } from "@/utils/format";
import type { ErrorEnvelope } from "@/types/core";
import type { MaterialRequestListItem } from "@/types/stock";

const router = useRouter();
const store = useStockStore();
const { items, total, page, pageSize, loading, fetchList, goToPage } =
  useList<MaterialRequestListItem>("/material-requests");

const showForm = ref(false);
const postingDate = ref(new Date().toISOString().slice(0, 10));
const scheduleDate = ref("");
const rows = ref<Array<{ item_id: string; qty: number }>>([{ item_id: "", qty: 1 }]);
const error = ref<ErrorEnvelope | null>(null);
const saving = ref(false);

const columns: Column[] = [
  { key: "name", label: "Request" },
  { key: "posting_date", label: "Date" },
  { key: "material_request_type", label: "Type" },
  { key: "per_ordered", label: "Ordered", class: "text-right" },
  { key: "status", label: "Status" },
];

async function save(): Promise<void> {
  saving.value = true;
  error.value = null;
  let created: string | null = null;
  try {
    const resp = await api.post<{ id: string }>("/material-requests", {
      posting_date: postingDate.value,
      schedule_date: scheduleDate.value || null,
      items: rows.value.filter((r) => r.item_id),
    });
    created = resp.data.id;
    await api.post(`/material-requests/${created}/submit`);
    showForm.value = false;
    rows.value = [{ item_id: "", qty: 1 }];
  } catch (e) {
    error.value = e as ErrorEnvelope;
    if (created) showForm.value = false; // draft saved — retry via the row action
  } finally {
    saving.value = false;
    await fetchList();
  }
}

async function submitDraft(row: MaterialRequestListItem): Promise<void> {
  error.value = null;
  try {
    await api.post(`/material-requests/${row.id}/submit`);
    await fetchList();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

function orderIt(row: MaterialRequestListItem): void {
  void router.push({ name: "purchase-order-new", query: { material_request_id: row.id } });
}

onMounted(async () => {
  await Promise.all([fetchList(), store.fetchItems()]);
});
</script>

<template>
  <div>
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">Material Requests</h1>
        <p class="text-sm text-gray-500">{{ total }} total</p>
      </div>
      <button class="btn-primary" @click="showForm = !showForm">
        {{ showForm ? "Close" : "New Request" }}
      </button>
    </div>

    <form v-if="showForm" class="mb-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm" @submit.prevent="save">
      <div class="mb-3 grid grid-cols-3 gap-4">
        <div>
          <label class="form-label">Date*</label>
          <input v-model="postingDate" type="date" required class="form-input" />
        </div>
        <div>
          <label class="form-label">Required By</label>
          <input v-model="scheduleDate" type="date" class="form-input" />
        </div>
      </div>
      <div v-for="(row, i) in rows" :key="i" class="mb-2 grid grid-cols-12 gap-2">
        <select v-model="row.item_id" class="form-input col-span-8">
          <option value="" disabled>Item…</option>
          <option v-for="opt in store.itemOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <input v-model.number="row.qty" type="number" min="0" step="any" placeholder="Qty" class="form-input col-span-4" />
      </div>
      <button type="button" class="btn-secondary" @click="rows.push({ item_id: '', qty: 1 })">Add Row</button>
      <p v-if="error" class="mt-2 text-sm text-red-600">{{ error.detail }}</p>
      <div class="mt-4 flex justify-end">
        <button type="submit" class="btn-primary" :disabled="saving">
          {{ saving ? "Saving…" : "Save & Submit" }}
        </button>
      </div>
    </form>

    <DataTable :columns="columns" :rows="items" :loading="loading">
      <template #cell-name="{ row }">
        <span class="font-medium text-gray-900">{{ row.name }}</span>
      </template>
      <template #cell-posting_date="{ value }">
        {{ formatDate(String(value)) }}
      </template>
      <template #cell-per_ordered="{ value }">
        {{ formatQty(value as string) }}%
      </template>
      <template #cell-status="{ value, row }">
        <div class="flex items-center gap-2">
          <StatusBadge :status="String(value)" />
          <button v-if="row.docstatus === 0" class="text-xs text-primary hover:underline"
                  @click.stop="submitDraft(row)">submit</button>
          <button v-if="row.docstatus === 1 && row.status !== 'Ordered'"
                  class="text-xs text-primary hover:underline"
                  @click.stop="orderIt(row)">order</button>
        </div>
      </template>
    </DataTable>
    <PaginationFooter :page="page" :page-size="pageSize" :total="total" @go-to="goToPage" />
  </div>
</template>
