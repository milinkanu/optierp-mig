<script setup lang="ts">
// Reorder: items below their reorder level, with one-click "draft a Material Request".

import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client";
import { formatQty } from "@/utils/format";
import type { ErrorEnvelope } from "@/types/core";
import type { ReorderRow } from "@/types/stock";

const router = useRouter();
const rows = ref<ReorderRow[]>([]);
const selected = ref<Set<string>>(new Set());
const loading = ref(false);
const saving = ref(false);
const error = ref<ErrorEnvelope | null>(null);

const allSelected = computed(() => rows.value.length > 0 && selected.value.size === rows.value.length);

function toggleAll(): void {
  selected.value = allSelected.value ? new Set() : new Set(rows.value.map((r) => r.item_id));
}
function toggle(id: string): void {
  const next = new Set(selected.value);
  next.has(id) ? next.delete(id) : next.add(id);
  selected.value = next;
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    rows.value = (await api.get<ReorderRow[]>("/stock-reorder")).data;
    selected.value = new Set(rows.value.map((r) => r.item_id)); // default: all
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    loading.value = false;
  }
}

async function createMaterialRequest(): Promise<void> {
  if (!selected.value.size) return;
  saving.value = true;
  error.value = null;
  try {
    const resp = await api.post<{ id: string; name: string }>("/stock-reorder/material-request", {
      item_ids: [...selected.value],
    });
    // a draft MR was created — take the user there to review & submit
    router.push({ path: "/material-requests", query: { created: resp.data.name } });
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div>
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">Reorder</h1>
        <p class="text-sm text-gray-500">
          Items below their reorder level (projected = on-hand + on-order − reserved)
        </p>
      </div>
      <button class="btn-primary" :disabled="saving || !selected.size" @click="createMaterialRequest">
        {{ saving ? "Creating…" : `Create Material Request (${selected.size})` }}
      </button>
    </div>

    <p v-if="error" class="mb-2 text-sm text-red-600">{{ error.detail }}</p>

    <div class="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      <table class="min-w-full text-sm">
        <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
          <tr>
            <th class="px-4 py-2 w-8">
              <input type="checkbox" :checked="allSelected" @change="toggleAll" />
            </th>
            <th class="px-4 py-2">Item</th>
            <th class="px-4 py-2">Default Warehouse</th>
            <th class="px-4 py-2 text-right">Projected</th>
            <th class="px-4 py-2 text-right">Reorder Level</th>
            <th class="px-4 py-2 text-right">Suggested Qty</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.item_id" class="border-t border-gray-100">
            <td class="px-4 py-2">
              <input type="checkbox" :checked="selected.has(row.item_id)" @change="toggle(row.item_id)" />
            </td>
            <td class="px-4 py-2 font-medium text-gray-900">{{ row.item_code }} — {{ row.item_name }}</td>
            <td class="px-4 py-2 text-gray-500">{{ row.default_warehouse_name ?? "—" }}</td>
            <td class="px-4 py-2 text-right" :class="Number(row.projected_qty) < 0 ? 'text-red-700' : ''">
              {{ formatQty(row.projected_qty) }}
            </td>
            <td class="px-4 py-2 text-right">{{ formatQty(row.reorder_level) }}</td>
            <td class="px-4 py-2 text-right font-medium">{{ formatQty(row.suggested_qty) }}</td>
          </tr>
          <tr v-if="!loading && !rows.length">
            <td colspan="6" class="px-4 py-8 text-center text-gray-400">
              All items are above their reorder level. 🎉
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
