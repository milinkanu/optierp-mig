<script setup lang="ts">
// Warehouse master: list + inline create.

import { computed, onMounted, ref } from "vue";
import DataTable, { type Column } from "@/components/shared/DataTable.vue";
import { useStockStore } from "@/stores/stock";
import { api } from "@/api/client";
import type { ErrorEnvelope } from "@/types/core";

const store = useStockStore();
const showForm = ref(false);
const error = ref<ErrorEnvelope | null>(null);
const saving = ref(false);
const form = ref({ warehouse_name: "", parent_warehouse_id: "", is_group: false });

const columns: Column[] = [
  { key: "warehouse_name", label: "Warehouse" },
  { key: "warehouse_type", label: "Type" },
  { key: "is_group", label: "Kind" },
];

const groupWarehouses = computed(() => store.warehouses.filter((w) => w.is_group));

async function save(): Promise<void> {
  saving.value = true;
  error.value = null;
  try {
    await api.post("/warehouses", {
      warehouse_name: form.value.warehouse_name,
      parent_warehouse_id: form.value.parent_warehouse_id || null,
      is_group: form.value.is_group,
    });
    form.value = { warehouse_name: "", parent_warehouse_id: "", is_group: false };
    showForm.value = false;
    await store.fetchWarehouses();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    saving.value = false;
  }
}

onMounted(() => store.fetchWarehouses());
</script>

<template>
  <div class="max-w-4xl">
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">Warehouses</h1>
        <p class="text-sm text-gray-500">{{ store.warehouses.length }} total</p>
      </div>
      <button class="btn-primary" @click="showForm = !showForm">
        {{ showForm ? "Close" : "New Warehouse" }}
      </button>
    </div>

    <form v-if="showForm" class="mb-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm" @submit.prevent="save">
      <div class="grid grid-cols-3 gap-4">
        <div>
          <label class="form-label">Name*</label>
          <input v-model="form.warehouse_name" required class="form-input" placeholder="e.g. Main Store" />
        </div>
        <div>
          <label class="form-label">Parent (group)</label>
          <select v-model="form.parent_warehouse_id" class="form-input">
            <option value="">—</option>
            <option v-for="w in groupWarehouses" :key="w.id" :value="w.id">{{ w.warehouse_name }}</option>
          </select>
        </div>
        <div class="flex items-end pb-2">
          <label class="flex items-center gap-2 text-sm text-gray-700">
            <input v-model="form.is_group" type="checkbox" class="rounded border-gray-300" />
            Group node (holds other warehouses)
          </label>
        </div>
      </div>
      <p v-if="error" class="mt-2 text-sm text-red-600">{{ error.detail }}</p>
      <div class="mt-4 flex justify-end">
        <button type="submit" class="btn-primary" :disabled="saving || !form.warehouse_name">
          {{ saving ? "Saving…" : "Create Warehouse" }}
        </button>
      </div>
    </form>

    <DataTable :columns="columns" :rows="store.warehouses" :loading="false">
      <template #cell-warehouse_name="{ row }">
        <span class="font-medium text-gray-900">{{ row.warehouse_name }}</span>
      </template>
      <template #cell-warehouse_type="{ value }">
        {{ value ?? "—" }}
      </template>
      <template #cell-is_group="{ value }">
        <span class="rounded-full px-2 py-0.5 text-xs font-medium"
              :class="value ? 'bg-purple-50 text-purple-700' : 'bg-gray-100 text-gray-600'">
          {{ value ? "Group" : "Storage" }}
        </span>
      </template>
    </DataTable>
  </div>
</template>
