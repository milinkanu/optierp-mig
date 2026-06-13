<script setup lang="ts">
// Stock Entry: list + create (Receipt / Issue / Transfer) with submit/cancel.

import { computed, onMounted, ref } from "vue";
import DataTable, { type Column } from "@/components/shared/DataTable.vue";
import PaginationFooter from "@/components/shared/PaginationFooter.vue";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import { useList } from "@/composables/useList";
import { useCompanyCurrency } from "@/composables/useCompanyCurrency";
import { useStockStore } from "@/stores/stock";
import { api } from "@/api/client";
import { formatCurrency, formatDate } from "@/utils/format";
import type { ErrorEnvelope } from "@/types/core";
import type { StockEntryItemIn, StockEntryListItem } from "@/types/stock";

const store = useStockStore();
const companyCurrency = useCompanyCurrency();
const { items, total, page, pageSize, loading, fetchList, goToPage } =
  useList<StockEntryListItem>("/stock-entries");

const showForm = ref(false);
const purpose = ref<"Material Receipt" | "Material Issue" | "Material Transfer">("Material Receipt");
const postingDate = ref(new Date().toISOString().slice(0, 10));
const fromWarehouseId = ref("");
const toWarehouseId = ref("");
const remarks = ref("");
const rows = ref<StockEntryItemIn[]>([{ item_id: "", qty: 1, basic_rate: 0 }]);
const error = ref<ErrorEnvelope | null>(null);
const saving = ref(false);

const needsSource = computed(() => purpose.value !== "Material Receipt");
const needsTarget = computed(() => purpose.value !== "Material Issue");
const showRate = computed(() => purpose.value === "Material Receipt");

const columns: Column[] = [
  { key: "name", label: "Entry" },
  { key: "posting_date", label: "Date" },
  { key: "purpose", label: "Purpose" },
  { key: "total_amount", label: "Amount", class: "text-right" },
  { key: "docstatus", label: "Status" },
];

async function save(): Promise<void> {
  saving.value = true;
  error.value = null;
  let created: string | null = null;
  try {
    const resp = await api.post<{ id: string }>("/stock-entries", {
      purpose: purpose.value,
      posting_date: postingDate.value,
      from_warehouse_id: needsSource.value ? fromWarehouseId.value || null : null,
      to_warehouse_id: needsTarget.value ? toWarehouseId.value || null : null,
      remarks: remarks.value || null,
      items: rows.value.filter((r) => r.item_id),
    });
    created = resp.data.id;
    await api.post(`/stock-entries/${created}/submit`);
    showForm.value = false;
    rows.value = [{ item_id: "", qty: 1, basic_rate: 0 }];
  } catch (e) {
    error.value = e as ErrorEnvelope;
    // a draft was created but failed to submit: surface it in the list with
    // its own submit action instead of risking a duplicate re-create
    if (created) showForm.value = false;
  } finally {
    saving.value = false;
    await fetchList();
  }
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

onMounted(async () => {
  await Promise.all([fetchList(), store.fetchItems(), store.fetchWarehouses()]);
});
</script>

<template>
  <div>
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">Stock Entries</h1>
        <p class="text-sm text-gray-500">{{ total }} total</p>
      </div>
      <button class="btn-primary" @click="showForm = !showForm">
        {{ showForm ? "Close" : "New Stock Entry" }}
      </button>
    </div>

    <form v-if="showForm" class="mb-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm" @submit.prevent="save">
      <div class="mb-3 grid grid-cols-4 gap-4">
        <div>
          <label class="form-label">Purpose*</label>
          <select v-model="purpose" class="form-input">
            <option>Material Receipt</option>
            <option>Material Issue</option>
            <option>Material Transfer</option>
          </select>
        </div>
        <div>
          <label class="form-label">Posting Date*</label>
          <input v-model="postingDate" type="date" required class="form-input" />
        </div>
        <div v-if="needsSource">
          <label class="form-label">From Warehouse*</label>
          <select v-model="fromWarehouseId" required class="form-input">
            <option value="" disabled>Select…</option>
            <option v-for="w in store.leafWarehouses" :key="w.id" :value="w.id">{{ w.warehouse_name }}</option>
          </select>
        </div>
        <div v-if="needsTarget">
          <label class="form-label">To Warehouse*</label>
          <select v-model="toWarehouseId" required class="form-input">
            <option value="" disabled>Select…</option>
            <option v-for="w in store.leafWarehouses" :key="w.id" :value="w.id">{{ w.warehouse_name }}</option>
          </select>
        </div>
      </div>
      <div v-for="(row, i) in rows" :key="i" class="mb-2 grid grid-cols-12 gap-2">
        <select v-model="row.item_id" class="form-input col-span-6">
          <option value="" disabled>Item…</option>
          <option v-for="opt in store.itemOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <input v-model.number="row.qty" type="number" min="0" step="any" placeholder="Qty" class="form-input col-span-3" />
        <input v-if="showRate" v-model.number="row.basic_rate" type="number" min="0" step="any"
               placeholder="Rate" class="form-input col-span-3" />
        <div v-else class="col-span-3 flex items-center pl-2 text-xs text-gray-400">at current valuation</div>
      </div>
      <div class="mt-2 flex items-center justify-between">
        <button type="button" class="btn-secondary" @click="rows.push({ item_id: '', qty: 1, basic_rate: 0 })">
          Add Row
        </button>
        <input v-model="remarks" class="form-input w-72" placeholder="Remarks (optional)" />
      </div>
      <p v-if="error" class="mt-2 text-sm text-red-600">{{ error.detail }}</p>
      <div class="mt-4 flex justify-end">
        <button type="submit" class="btn-primary" :disabled="saving">
          {{ saving ? "Posting…" : "Save & Submit" }}
        </button>
      </div>
    </form>
    <p v-if="!showForm && error" class="mb-2 text-sm text-red-600">{{ error.detail }}</p>

    <DataTable :columns="columns" :rows="items" :loading="loading">
      <template #cell-name="{ row }">
        <span class="font-medium text-gray-900">{{ row.name }}</span>
      </template>
      <template #cell-posting_date="{ value }">
        {{ formatDate(String(value)) }}
      </template>
      <template #cell-total_amount="{ value }">
        {{ formatCurrency(String(value), companyCurrency) }}
      </template>
      <template #cell-docstatus="{ value, row }">
        <div class="flex items-center gap-2">
          <StatusBadge :status="Number(value)" />
          <button v-if="value === 0" class="text-xs text-primary hover:underline"
                  @click.stop="rowAction(row, 'submit')">submit</button>
          <button v-if="value === 1" class="text-xs text-red-600 hover:underline"
                  @click.stop="rowAction(row, 'cancel')">cancel</button>
        </div>
      </template>
    </DataTable>
    <PaginationFooter :page="page" :page-size="pageSize" :total="total" @go-to="goToPage" />
  </div>
</template>
