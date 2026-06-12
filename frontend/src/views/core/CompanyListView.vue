<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import DataTable, { type Column } from "@/components/shared/DataTable.vue";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import { useList } from "@/composables/useList";
import { usePermissions } from "@/composables/usePermissions";
import type { CompanyListItem } from "@/types/core";

const router = useRouter();
const { hasRole } = usePermissions();
const { items, total, loading, fetchList } = useList<CompanyListItem>("/companies");

const columns: Column[] = [
  { key: "company_name", label: "Company" },
  { key: "abbr", label: "Abbr" },
  { key: "default_currency", label: "Currency" },
  { key: "country_code", label: "Country" },
  { key: "enabled", label: "Status" },
];

onMounted(() => void fetchList());
</script>

<template>
  <div>
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">Companies</h1>
        <p class="text-sm text-gray-500">{{ total }} total</p>
      </div>
      <button
        v-if="hasRole('System Manager')"
        class="btn-primary"
        @click="router.push({ name: 'company-new' })"
      >
        New Company
      </button>
    </div>
    <DataTable
      :columns="columns"
      :rows="items"
      :loading="loading"
      @row-click="(row) => router.push({ name: 'company-detail', params: { id: row.id } })"
    >
      <template #cell-enabled="{ value }">
        <StatusBadge :status="Boolean(value)" />
      </template>
    </DataTable>
  </div>
</template>
