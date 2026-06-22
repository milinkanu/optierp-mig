<script setup lang="ts">
// Asset detail: header + book-value summary + the depreciation schedule. Submit a
// draft, then "Depreciate now" posts every due row (schedule_date ≤ today) as a
// balanced Journal Entry — idempotent, so posted rows are skipped on a re-run.
import { onMounted, ref } from "vue";
import { api } from "@/api/client";
import { formatCurrency, formatDate } from "@/utils/format";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import type { ErrorEnvelope } from "@/types/core";

const props = defineProps<{ id: string }>();

interface ScheduleRow {
  id: string;
  idx: number;
  schedule_date: string;
  depreciation_amount: string;
  accumulated_depreciation: string;
  posted: boolean;
  posted_date: string | null;
  journal_entry_id: string | null;
}
interface Asset {
  id: string;
  name: string;
  asset_name: string;
  category_name: string | null;
  location_name: string | null;
  depreciation_method: string | null;
  custodian: string | null;
  gross_purchase_amount: string;
  opening_accumulated_depreciation: string;
  accumulated_depreciation: string;
  book_value: string;
  purchase_date: string | null;
  available_for_use_date: string;
  status: string;
  remarks: string | null;
  schedule: ScheduleRow[];
}

const asset = ref<Asset | null>(null);
const loading = ref(false);
const busy = ref(false);
const error = ref<ErrorEnvelope | null>(null);
const notice = ref<string | null>(null);

async function fetchAsset(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    asset.value = (await api.get<Asset>(`/assets/${props.id}`)).data;
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    loading.value = false;
  }
}

async function act(action: "submit" | "cancel"): Promise<void> {
  busy.value = true;
  error.value = null;
  notice.value = null;
  try {
    await api.post(`/assets/${props.id}/${action}`);
    await fetchAsset();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    busy.value = false;
  }
}

async function depreciate(): Promise<void> {
  busy.value = true;
  error.value = null;
  notice.value = null;
  try {
    const res = (
      await api.post<{ posted_count: number }>(`/assets/${props.id}/depreciate`)
    ).data;
    notice.value =
      res.posted_count > 0
        ? `Posted ${res.posted_count} depreciation entr${res.posted_count === 1 ? "y" : "ies"}.`
        : "Nothing due to depreciate right now.";
    await fetchAsset();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    busy.value = false;
  }
}

onMounted(fetchAsset);
</script>

<template>
  <div v-if="asset">
    <div class="mb-4 flex items-start justify-between">
      <div>
        <RouterLink to="/assets" class="text-sm text-blue-600 hover:underline">← Assets</RouterLink>
        <h1 class="mt-1 text-xl font-semibold text-gray-900">
          {{ asset.asset_name }}
          <span class="ml-2 align-middle"><StatusBadge :status="asset.status" /></span>
        </h1>
        <p class="text-sm text-gray-400">{{ asset.name }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button v-if="asset.status === 'Draft'" class="btn-primary" :disabled="busy" @click="act('submit')">
          Submit
        </button>
        <button
          v-if="asset.status === 'Submitted' || asset.status === 'Partially Depreciated'"
          class="btn-primary"
          :disabled="busy"
          @click="depreciate"
        >
          Depreciate now
        </button>
        <button
          v-if="asset.status === 'Submitted'"
          class="rounded-md border border-red-200 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50"
          :disabled="busy"
          @click="act('cancel')"
        >
          Cancel
        </button>
      </div>
    </div>

    <p v-if="notice" class="mb-3 rounded bg-green-50 px-3 py-2 text-sm text-green-700">{{ notice }}</p>
    <p v-if="error" class="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-600">{{ error.detail }}</p>

    <!-- summary cards -->
    <div class="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
      <div class="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <div class="text-xs uppercase text-gray-400">Cost</div>
        <div class="text-lg font-semibold text-gray-900">{{ formatCurrency(asset.gross_purchase_amount) }}</div>
      </div>
      <div class="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <div class="text-xs uppercase text-gray-400">Accumulated Depreciation</div>
        <div class="text-lg font-semibold text-gray-900">{{ formatCurrency(asset.accumulated_depreciation) }}</div>
      </div>
      <div class="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <div class="text-xs uppercase text-gray-400">Book Value</div>
        <div class="text-lg font-semibold text-primary">{{ formatCurrency(asset.book_value) }}</div>
      </div>
      <div class="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <div class="text-xs uppercase text-gray-400">Method</div>
        <div class="text-lg font-semibold text-gray-900">{{ asset.depreciation_method ?? "—" }}</div>
      </div>
    </div>

    <!-- meta -->
    <div class="mb-6 grid grid-cols-2 gap-x-8 gap-y-2 rounded-lg border border-gray-200 bg-white p-5 text-sm shadow-sm md:grid-cols-3">
      <div><span class="text-gray-400">Category:</span> {{ asset.category_name ?? "—" }}</div>
      <div><span class="text-gray-400">Location:</span> {{ asset.location_name ?? "—" }}</div>
      <div><span class="text-gray-400">Custodian:</span> {{ asset.custodian ?? "—" }}</div>
      <div><span class="text-gray-400">Purchase date:</span> {{ formatDate(asset.purchase_date) }}</div>
      <div><span class="text-gray-400">Available for use:</span> {{ formatDate(asset.available_for_use_date) }}</div>
      <div><span class="text-gray-400">Opening accum. dep.:</span> {{ formatCurrency(asset.opening_accumulated_depreciation) }}</div>
    </div>

    <!-- schedule -->
    <h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">Depreciation Schedule</h2>
    <div class="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      <table class="min-w-full text-sm">
        <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
          <tr>
            <th class="px-4 py-2">#</th>
            <th class="px-4 py-2">Date</th>
            <th class="px-4 py-2 text-right">Depreciation</th>
            <th class="px-4 py-2 text-right">Accumulated</th>
            <th class="px-4 py-2">Posted</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in asset.schedule" :key="row.id" class="border-t border-gray-100" :class="{ 'bg-green-50/40': row.posted }">
            <td class="px-4 py-1.5 text-gray-400">{{ row.idx }}</td>
            <td class="px-4 py-1.5">{{ formatDate(row.schedule_date) }}</td>
            <td class="px-4 py-1.5 text-right">{{ formatCurrency(row.depreciation_amount) }}</td>
            <td class="px-4 py-1.5 text-right text-gray-500">{{ formatCurrency(row.accumulated_depreciation) }}</td>
            <td class="px-4 py-1.5">
              <span v-if="row.posted" class="text-xs font-medium text-green-700">
                ✓ {{ formatDate(row.posted_date) }}
              </span>
              <span v-else class="text-xs text-gray-400">pending</span>
            </td>
          </tr>
          <tr v-if="!asset.schedule.length">
            <td colspan="5" class="px-4 py-8 text-center text-gray-400">No schedule rows.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
  <div v-else-if="loading" class="py-12 text-center text-gray-400">Loading…</div>
  <div v-else class="py-12 text-center text-gray-400">Asset not found.</div>
</template>
