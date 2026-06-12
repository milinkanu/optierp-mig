<script setup lang="ts">
import { onMounted } from "vue";
import DataTable, { type Column } from "@/components/shared/DataTable.vue";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import { useCoreStore } from "@/stores/core";

const core = useCoreStore();

const columns: Column[] = [
  { key: "name", label: "Role" },
  { key: "description", label: "Description" },
  { key: "is_system", label: "Type" },
  { key: "disabled", label: "Status" },
];

onMounted(() => void core.fetchRoles());
</script>

<template>
  <div>
    <h1 class="mb-4 text-xl font-semibold text-gray-900">Roles</h1>
    <DataTable :columns="columns" :rows="core.roles">
      <template #cell-is_system="{ value }">
        <span class="text-xs text-gray-500">{{ value ? "System" : "Custom" }}</span>
      </template>
      <template #cell-disabled="{ value }">
        <StatusBadge :status="value ? 'Disabled' : 'Active'" />
      </template>
    </DataTable>
  </div>
</template>
