<script setup lang="ts">
// Item master: searchable list + inline create form.

import { onMounted, ref } from "vue";
import DataTable, { type Column } from "@/components/shared/DataTable.vue";
import PaginationFooter from "@/components/shared/PaginationFooter.vue";
import { useList } from "@/composables/useList";
import { useStockStore } from "@/stores/stock";
import { formatCurrency } from "@/utils/format";
import { useCompanyCurrency } from "@/composables/useCompanyCurrency";
import type { ErrorEnvelope } from "@/types/core";
import type { ItemListItem } from "@/types/stock";

const store = useStockStore();
const companyCurrency = useCompanyCurrency();
const { items, total, page, pageSize, loading, filters, fetchList, goToPage } =
  useList<ItemListItem>("/items");

const showForm = ref(false);
const search = ref("");
const error = ref<ErrorEnvelope | null>(null);
const saving = ref(false);

const form = ref({
  item_code: "",
  item_name: "",
  item_group_id: "",
  stock_uom: "Nos",
  standard_rate: 0,
  valuation_rate: 0,
  default_warehouse_id: "",
  is_stock_item: true,
});

const columns: Column[] = [
  { key: "item_code", label: "Item Code" },
  { key: "item_name", label: "Name" },
  { key: "item_group_name", label: "Group" },
  { key: "stock_uom", label: "UOM" },
  { key: "standard_rate", label: "Selling Rate", class: "text-right" },
  { key: "is_stock_item", label: "Type" },
];

async function applySearch(): Promise<void> {
  filters.value = search.value ? { search: search.value } : {};
  page.value = 1;
  await fetchList();
}

async function save(): Promise<void> {
  saving.value = true;
  error.value = null;
  try {
    await store.createItem({
      item_code: form.value.item_code,
      item_name: form.value.item_name || form.value.item_code,
      item_group_id: form.value.item_group_id || null,
      stock_uom: form.value.stock_uom || "Nos",
      standard_rate: form.value.standard_rate || 0,
      valuation_rate: form.value.valuation_rate || 0,
      default_warehouse_id: form.value.default_warehouse_id || null,
      is_stock_item: form.value.is_stock_item,
    });
    showForm.value = false;
    form.value = {
      item_code: "", item_name: "", item_group_id: "", stock_uom: "Nos",
      standard_rate: 0, valuation_rate: 0, default_warehouse_id: "", is_stock_item: true,
    };
    await fetchList();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  await Promise.all([fetchList(), store.fetchWarehouses(), store.fetchItemGroups()]);
});
</script>

<template>
  <div>
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">Items</h1>
        <p class="text-sm text-gray-500">{{ total }} total</p>
      </div>
      <div class="flex items-center gap-3">
        <input v-model="search" class="form-input w-56" placeholder="Search code or name…"
               @keyup.enter="applySearch" />
        <button class="btn-primary" @click="showForm = !showForm">
          {{ showForm ? "Close" : "New Item" }}
        </button>
      </div>
    </div>

    <form v-if="showForm" class="mb-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm" @submit.prevent="save">
      <div class="grid grid-cols-4 gap-4">
        <div>
          <label class="form-label">Item Code*</label>
          <input v-model="form.item_code" required class="form-input" placeholder="e.g. WIDGET-01" />
        </div>
        <div>
          <label class="form-label">Item Name</label>
          <input v-model="form.item_name" class="form-input" placeholder="defaults to code" />
        </div>
        <div>
          <label class="form-label">Item Group</label>
          <select v-model="form.item_group_id" class="form-input">
            <option value="">—</option>
            <option v-for="g in store.itemGroups" :key="g.id" :value="g.id">{{ g.item_group_name }}</option>
          </select>
        </div>
        <div>
          <label class="form-label">Unit of Measure</label>
          <input v-model="form.stock_uom" class="form-input" placeholder="Nos" />
        </div>
        <div>
          <label class="form-label">Selling Rate</label>
          <input v-model.number="form.standard_rate" type="number" min="0" step="any" class="form-input" />
        </div>
        <div>
          <label class="form-label">Opening Valuation Rate</label>
          <input v-model.number="form.valuation_rate" type="number" min="0" step="any" class="form-input" />
        </div>
        <div>
          <label class="form-label">Default Warehouse</label>
          <select v-model="form.default_warehouse_id" class="form-input">
            <option value="">—</option>
            <option v-for="w in store.leafWarehouses" :key="w.id" :value="w.id">{{ w.warehouse_name }}</option>
          </select>
        </div>
        <div class="flex items-end pb-2">
          <label class="flex items-center gap-2 text-sm text-gray-700">
            <input v-model="form.is_stock_item" type="checkbox" class="rounded border-gray-300" />
            Maintain stock for this item
          </label>
        </div>
      </div>
      <p v-if="error" class="mt-2 text-sm text-red-600">{{ error.detail }}</p>
      <div class="mt-4 flex justify-end">
        <button type="submit" class="btn-primary" :disabled="saving || !form.item_code">
          {{ saving ? "Saving…" : "Create Item" }}
        </button>
      </div>
    </form>

    <DataTable :columns="columns" :rows="items" :loading="loading">
      <template #cell-item_code="{ row }">
        <span class="font-medium text-gray-900">{{ row.item_code }}</span>
      </template>
      <template #cell-item_group_name="{ value }">
        {{ value ?? "—" }}
      </template>
      <template #cell-standard_rate="{ value }">
        {{ formatCurrency(String(value), companyCurrency) }}
      </template>
      <template #cell-is_stock_item="{ value }">
        <span class="rounded-full px-2 py-0.5 text-xs font-medium"
              :class="value ? 'bg-blue-50 text-blue-700' : 'bg-gray-100 text-gray-600'">
          {{ value ? "Stock" : "Service" }}
        </span>
      </template>
    </DataTable>
    <PaginationFooter :page="page" :page-size="pageSize" :total="total" @go-to="goToPage" />
  </div>
</template>
