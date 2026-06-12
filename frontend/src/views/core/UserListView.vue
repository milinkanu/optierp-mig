<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import DataTable, { type Column } from "@/components/shared/DataTable.vue";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import { useList } from "@/composables/useList";
import { usePermissions } from "@/composables/usePermissions";
import type { UserListItem } from "@/types/core";

const router = useRouter();
const { hasRole } = usePermissions();
const { items, total, loading, filters, fetchList } = useList<UserListItem>("/users");
const search = ref("");

let debounce: ReturnType<typeof setTimeout> | undefined;
watch(search, (value) => {
  clearTimeout(debounce);
  debounce = setTimeout(() => {
    filters.value.search = value || undefined;
    void fetchList();
  }, 300);
});

const columns: Column[] = [
  { key: "email", label: "Email" },
  { key: "first_name", label: "First Name" },
  { key: "last_name", label: "Last Name" },
  { key: "is_active", label: "Status" },
];

onMounted(() => void fetchList());
</script>

<template>
  <div>
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">Users</h1>
        <p class="text-sm text-gray-500">{{ total }} total</p>
      </div>
      <div class="flex gap-3">
        <input v-model="search" type="search" placeholder="Search users…" class="form-input w-64" />
        <button v-if="hasRole('System Manager')" class="btn-primary" @click="router.push({ name: 'user-new' })">
          New User
        </button>
      </div>
    </div>
    <DataTable :columns="columns" :rows="items" :loading="loading">
      <template #cell-is_active="{ value }">
        <StatusBadge :status="Boolean(value)" />
      </template>
    </DataTable>
  </div>
</template>
