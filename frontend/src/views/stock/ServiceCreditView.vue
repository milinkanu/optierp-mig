<script setup lang="ts">
// Service Credits: list of prepaid service blocks with remaining balances.

import { onMounted } from "vue";
import { useRouter } from "vue-router";
import DataTable, { type Column } from "@/components/shared/DataTable.vue";
import PaginationFooter from "@/components/shared/PaginationFooter.vue";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import { useList } from "@/composables/useList";
import { formatQty } from "@/utils/format";
import type { ServiceCreditListItem } from "@/types/stock";

const router = useRouter();
const { items, total, page, pageSize, loading, fetchList, goToPage } =
  useList<ServiceCreditListItem>("/service-credits");

const columns: Column[] = [
  { key: "name", label: "Credit" },
  { key: "item_code", label: "Service" },
  { key: "supplier_name", label: "Supplier" },
  { key: "purchased_qty", label: "Purchased", class: "text-right" },
  { key: "consumed_qty", label: "Used", class: "text-right" },
  { key: "balance_qty", label: "Remaining", class: "text-right" },
  { key: "status", label: "Status" },
];

function open(row: ServiceCreditListItem): void {
  router.push(`/service-credits/${row.id}`);
}

onMounted(fetchList);
</script>

<template>
  <div>
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">Service Credits</h1>
        <p class="text-sm text-gray-500">{{ total }} total · prepaid service units (e.g. support hours)</p>
      </div>
      <button class="btn-primary" @click="router.push('/service-credits/new')">New Service Credit</button>
    </div>

    <DataTable :columns="columns" :rows="items" :loading="loading">
      <template #cell-name="{ row }">
        <button class="font-medium text-primary hover:underline" @click="open(row)">{{ row.name }}</button>
      </template>
      <template #cell-item_code="{ row }">{{ row.item_code }} — {{ row.item_name }}</template>
      <template #cell-supplier_name="{ value }">{{ value ?? "—" }}</template>
      <template #cell-purchased_qty="{ row }">{{ formatQty(row.purchased_qty) }} {{ row.uom ?? "" }}</template>
      <template #cell-consumed_qty="{ value }">{{ formatQty(value as string) }}</template>
      <template #cell-balance_qty="{ value }">
        <span class="font-medium text-green-700">{{ formatQty(value as string) }}</span>
      </template>
      <template #cell-status="{ value }">
        <StatusBadge :status="String(value)" />
      </template>
    </DataTable>
    <PaginationFooter :page="page" :page-size="pageSize" :total="total" @go-to="goToPage" />
  </div>
</template>
