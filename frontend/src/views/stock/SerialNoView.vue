<script setup lang="ts">
// Serial No master list (read-only): serials are created/moved by stock
// transactions. Filter by status / search to look up a unit (warranty/RMA).
import { onMounted, ref } from "vue";
import DataTable, { type Column } from "@/components/shared/DataTable.vue";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import { api } from "@/api/client";
import type { ListResponse } from "@/types/core";

interface SerialRow {
  id: string;
  serial_no: string;
  item_code: string | null;
  item_name: string | null;
  status: string;
  warehouse_id: string | null;
}

const rows = ref<SerialRow[]>([]);
const total = ref(0);
const loading = ref(false);
const statusFilter = ref("");
const search = ref("");

const columns: Column[] = [
  { key: "serial_no", label: "Serial No" },
  { key: "item", label: "Item" },
  { key: "status", label: "Status" },
];

async function load(): Promise<void> {
  loading.value = true;
  try {
    const params: Record<string, unknown> = { page_size: 200 };
    if (statusFilter.value) params.status = statusFilter.value;
    if (search.value.trim()) params.search = search.value.trim();
    const resp = await api.get<ListResponse<SerialRow>>("/serial-nos", { params });
    rows.value = resp.data.items;
    total.value = resp.data.total;
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div>
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">Serial Numbers</h1>
        <p class="text-sm text-gray-500">{{ total }} tracked units · created by receipts, moved by deliveries</p>
      </div>
      <div class="flex gap-2">
        <input v-model="search" class="form-input w-48" placeholder="Search serial…" @keyup.enter="load" />
        <select v-model="statusFilter" class="form-input w-40" @change="load">
          <option value="">All statuses</option>
          <option>In Stock</option>
          <option>Delivered</option>
          <option>Returned</option>
        </select>
      </div>
    </div>
    <DataTable :columns="columns" :rows="rows" :loading="loading">
      <template #cell-serial_no="{ row }">
        <span class="font-mono text-gray-900">{{ row.serial_no }}</span>
      </template>
      <template #cell-item="{ row }">
        {{ row.item_code ? `${row.item_code} — ` : "" }}{{ row.item_name }}
      </template>
      <template #cell-status="{ value }">
        <StatusBadge :status="String(value)" />
      </template>
    </DataTable>
  </div>
</template>
