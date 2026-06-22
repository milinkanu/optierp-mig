<script setup lang="ts">
// Warehouse master — create + view/edit. is_group is set only at creation.

import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "@/api/client";
import { useStockStore } from "@/stores/stock";
import { useAccountsStore } from "@/stores/accounts";
import type { AccountNode, ErrorEnvelope } from "@/types/core";
import type { Warehouse } from "@/types/stock";

const route = useRoute();
const router = useRouter();
const store = useStockStore();
const accounts = useAccountsStore();

const whId = computed(() => route.params.id as string | undefined);
const isEdit = computed(() => !!whId.value);
const saving = ref(false);
const error = ref<ErrorEnvelope | null>(null);

const form = reactive({
  warehouse_name: "",
  parent_warehouse_id: "",
  is_group: false,
  warehouse_type: "",
  account_id: "",
  disabled: false,
});

const groupWarehouses = computed(() =>
  store.warehouses.filter((w) => w.is_group && w.id !== whId.value),
);
const assetAccounts = computed(() =>
  accounts.leafAccounts.filter((a: AccountNode) => a.root_type === "Asset"),
);

async function load(): Promise<void> {
  if (!whId.value) return;
  try {
    const { data } = await api.get<Warehouse>(`/warehouses/${whId.value}`);
    Object.assign(form, {
      warehouse_name: data.warehouse_name,
      parent_warehouse_id: data.parent_warehouse_id ?? "",
      is_group: data.is_group,
      warehouse_type: data.warehouse_type ?? "",
      account_id: data.account_id ?? "",
      disabled: data.disabled,
    });
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

async function save(): Promise<void> {
  saving.value = true;
  error.value = null;
  try {
    if (isEdit.value) {
      await api.patch(`/warehouses/${whId.value}`, {
        warehouse_name: form.warehouse_name,
        parent_warehouse_id: form.parent_warehouse_id || null,
        warehouse_type: form.warehouse_type || null,
        account_id: form.account_id || null,
        disabled: form.disabled,
      });
      await store.fetchWarehouses();
      await load();
    } else {
      const { data } = await api.post<Warehouse>("/warehouses", {
        warehouse_name: form.warehouse_name,
        parent_warehouse_id: form.parent_warehouse_id || null,
        is_group: form.is_group,
        warehouse_type: form.warehouse_type || null,
        account_id: form.account_id || null,
      });
      await store.fetchWarehouses();
      router.push(`/warehouses/${data.id}`);
    }
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  await Promise.all([store.fetchWarehouses(), accounts.fetchAccounts()]);
  await load();
});
</script>

<template>
  <div class="mx-auto max-w-2xl">
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">
          {{ isEdit ? form.warehouse_name : "New Warehouse" }}
        </h1>
        <p class="text-sm text-gray-500">
          <router-link to="/warehouses" class="text-primary hover:underline">Warehouses</router-link>
          <span v-if="form.is_group" class="ml-2 rounded-full bg-purple-50 px-2 py-0.5 text-xs text-purple-700">Group</span>
          <span v-if="form.disabled" class="ml-2 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">Disabled</span>
        </p>
      </div>
      <button class="btn-primary" :disabled="saving || !form.warehouse_name" @click="save">
        {{ saving ? "Saving…" : isEdit ? "Save" : "Create" }}
      </button>
    </div>

    <p v-if="error" class="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{{ error.detail }}</p>

    <section class="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      <div class="grid grid-cols-2 gap-4">
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
        <div>
          <label class="form-label">Warehouse Type</label>
          <input v-model="form.warehouse_type" class="form-input" placeholder="e.g. Stores, Transit" />
        </div>
        <div>
          <label class="form-label">Inventory Account (override)</label>
          <select v-model="form.account_id" class="form-input">
            <option value="">— company default —</option>
            <option v-for="a in assetAccounts" :key="a.id" :value="a.id">{{ a.account_name }}</option>
          </select>
        </div>
      </div>
      <div class="mt-3 flex flex-wrap gap-6">
        <label class="flex items-center gap-2 text-sm text-gray-700">
          <input v-model="form.is_group" type="checkbox" :disabled="isEdit" class="rounded border-gray-300" />
          Group node (holds other warehouses)
        </label>
        <label v-if="isEdit" class="flex items-center gap-2 text-sm text-gray-700">
          <input v-model="form.disabled" type="checkbox" class="rounded border-gray-300" />
          Disabled
        </label>
      </div>
    </section>
  </div>
</template>
