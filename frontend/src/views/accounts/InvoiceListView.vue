<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import DataTable, { type Column } from "@/components/shared/DataTable.vue";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import { useList } from "@/composables/useList";
import type { InvoiceListItem } from "@/types/accounts";

const props = defineProps<{ kind: "sales" | "purchase" }>();
const router = useRouter();

const endpoint = computed(() => (props.kind === "sales" ? "/sales-invoices" : "/purchase-invoices"));
const title = computed(() => (props.kind === "sales" ? "Sales Invoices" : "Purchase Invoices"));

const { items, total, loading, fetchList } = useList<InvoiceListItem>(endpoint.value);

const columns: Column[] = [
  { key: "name", label: "Invoice" },
  { key: "posting_date", label: "Date" },
  { key: "grand_total", label: "Grand Total", class: "text-right" },
  { key: "outstanding_amount", label: "Outstanding", class: "text-right" },
  { key: "status", label: "Status" },
];

onMounted(() => void fetchList());
watch(() => props.kind, () => router.go(0));
</script>

<template>
  <div>
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">{{ title }}</h1>
        <p class="text-sm text-gray-500">{{ total }} total</p>
      </div>
      <button class="btn-primary" @click="router.push(`${endpoint}/new`)">New Invoice</button>
    </div>
    <DataTable
      :columns="columns"
      :rows="items"
      :loading="loading"
      @row-click="(row) => router.push(`${endpoint}/${row.id}`)"
    >
      <template #cell-status="{ value }">
        <StatusBadge :status="String(value)" />
      </template>
    </DataTable>
  </div>
</template>
