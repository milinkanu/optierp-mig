<script setup lang="ts">
// ERPNext-style "Get Items From" control: a dropdown of upstream document types
// and a picker modal listing recent documents of the chosen type. Selecting one
// emits (param, id); the parent navigates with that query param so the form's
// existing prefill logic pulls the items in.

import { ref } from "vue";
import { api } from "@/api/client";
import { formatDate } from "@/utils/format";

export interface ItemSource {
  label: string; // e.g. "Quotation"
  param: string; // query param the form prefill reads, e.g. "quotation_id"
  endpoint: string; // list endpoint, e.g. "/quotations"
}

interface PickRow {
  id: string;
  name: string;
  posting_date?: string;
  status?: string;
  customer_name?: string | null;
  supplier_name?: string | null;
}

const props = defineProps<{ sources: ItemSource[] }>();
const emit = defineEmits<{ select: [param: string, id: string] }>();

const menuOpen = ref(false);
const active = ref<ItemSource | null>(null);
const rows = ref<PickRow[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

function toggleMenu(): void {
  if (props.sources.length === 0) return;
  menuOpen.value = !menuOpen.value;
}

async function choose(source: ItemSource): Promise<void> {
  menuOpen.value = false;
  active.value = source;
  loading.value = true;
  error.value = null;
  rows.value = [];
  try {
    const resp = await api.get<{ items?: PickRow[] } | PickRow[]>(source.endpoint, {
      params: { page_size: 50 },
    });
    const data = resp.data;
    rows.value = Array.isArray(data) ? data : (data.items ?? []);
  } catch {
    error.value = "Could not load documents.";
  } finally {
    loading.value = false;
  }
}

function pick(row: PickRow): void {
  if (active.value) emit("select", active.value.param, row.id);
  close();
}
function close(): void {
  active.value = null;
  rows.value = [];
  error.value = null;
}
</script>

<template>
  <div class="relative">
    <button
      type="button"
      class="btn-secondary gap-1"
      :disabled="sources.length === 0"
      :title="sources.length === 0 ? 'No source documents available' : ''"
      @click="toggleMenu"
    >
      Get Items From
      <span class="text-xs text-gray-400">▾</span>
    </button>

    <!-- dropdown -->
    <div
      v-if="menuOpen"
      class="absolute right-0 z-30 mt-1 w-52 overflow-hidden rounded-md border border-gray-200 bg-white py-1 shadow-lg"
    >
      <button
        v-for="source in sources"
        :key="source.param"
        type="button"
        class="block w-full px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
        @click="choose(source)"
      >
        {{ source.label }}
      </button>
    </div>
    <!-- click-away for the dropdown -->
    <div v-if="menuOpen" class="fixed inset-0 z-20" @click="menuOpen = false"></div>

    <!-- picker modal -->
    <div
      v-if="active"
      class="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4"
      @click.self="close"
    >
      <div class="w-full max-w-xl rounded-lg bg-white shadow-xl">
        <div class="flex items-center justify-between border-b border-gray-200 px-5 py-3">
          <h3 class="text-sm font-semibold text-gray-900">Select {{ active.label }}</h3>
          <button type="button" class="text-gray-400 hover:text-gray-700" @click="close">✕</button>
        </div>
        <div class="max-h-96 overflow-y-auto">
          <p v-if="loading" class="px-5 py-6 text-center text-sm text-gray-400">Loading…</p>
          <p v-else-if="error" class="px-5 py-6 text-center text-sm text-red-600">{{ error }}</p>
          <p v-else-if="rows.length === 0" class="px-5 py-6 text-center text-sm text-gray-400">
            No {{ active.label }} documents found.
          </p>
          <button
            v-for="row in rows"
            v-else
            :key="row.id"
            type="button"
            class="flex w-full items-center justify-between border-b border-gray-100 px-5 py-3 text-left text-sm last:border-b-0 hover:bg-gray-50"
            @click="pick(row)"
          >
            <span>
              <span class="font-medium text-gray-900">{{ row.name }}</span>
              <span v-if="row.customer_name || row.supplier_name" class="ml-2 text-gray-500">
                {{ row.customer_name ?? row.supplier_name }}
              </span>
            </span>
            <span class="flex items-center gap-3 text-xs text-gray-500">
              <span v-if="row.posting_date">{{ formatDate(row.posting_date) }}</span>
              <span v-if="row.status" class="rounded-full bg-gray-100 px-2 py-0.5">{{ row.status }}</span>
            </span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
