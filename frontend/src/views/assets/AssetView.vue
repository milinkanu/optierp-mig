<script setup lang="ts">
// Asset register: fixed assets with a generated depreciation schedule. Creating an
// asset (Draft) auto-builds its straight-line schedule; submit, then post depreciation
// from the asset's detail page. Define Asset Categories (method + accounts) and
// Locations first — they are engine masters.
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client";
import { formatCurrency } from "@/utils/format";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import type { ErrorEnvelope, ListResponse } from "@/types/core";

interface AssetRow {
  id: string;
  name: string;
  asset_name: string;
  category_name: string | null;
  location_name: string | null;
  gross_purchase_amount: string;
  accumulated_depreciation: string;
  book_value: string;
  status: string;
}
interface CategoryOpt { id: string; category_name: string; depreciation_method: string }
interface LocationOpt { id: string; location_name: string }

const router = useRouter();

const rows = ref<AssetRow[]>([]);
const categories = ref<CategoryOpt[]>([]);
const locations = ref<LocationOpt[]>([]);
const loading = ref(false);
const error = ref<ErrorEnvelope | null>(null);

const showForm = ref(false);
const today = new Date().toISOString().slice(0, 10);
const fName = ref("");
const fCategory = ref("");
const fLocation = ref("");
const fCustodian = ref("");
const fGross = ref<number | null>(null);
const fOpening = ref<number>(0);
const fPurchaseDate = ref(today);
const fInUseDate = ref(today);
const fRemarks = ref("");
const saving = ref(false);

async function fetchOptions(): Promise<void> {
  const [cat, loc] = await Promise.all([
    api.get<ListResponse<CategoryOpt>>("/registry/asset-category", { params: { page_size: 200 } }),
    api.get<ListResponse<LocationOpt>>("/registry/location", { params: { page_size: 200 } }),
  ]);
  categories.value = cat.data.items;
  locations.value = loc.data.items;
}

async function fetchList(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    rows.value = (
      await api.get<ListResponse<AssetRow>>("/assets", { params: { page_size: 100 } })
    ).data.items;
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    loading.value = false;
  }
}

async function save(): Promise<void> {
  if (!fName.value || !fCategory.value || !fGross.value) return;
  saving.value = true;
  error.value = null;
  try {
    const created = (
      await api.post<{ id: string }>("/assets", {
        asset_name: fName.value,
        asset_category_id: fCategory.value,
        location_id: fLocation.value || null,
        custodian: fCustodian.value || null,
        gross_purchase_amount: fGross.value,
        opening_accumulated_depreciation: fOpening.value || 0,
        purchase_date: fPurchaseDate.value || null,
        available_for_use_date: fInUseDate.value,
        remarks: fRemarks.value || null,
      })
    ).data;
    // jump to the detail page so the generated schedule is visible immediately
    void router.push(`/assets/${created.id}`);
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  await Promise.all([fetchOptions(), fetchList()]);
});
</script>

<template>
  <div>
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">Assets</h1>
        <p class="text-sm text-gray-500">
          Your fixed assets (vehicles, machinery, computers) and their depreciation. Creating an asset
          builds its depreciation schedule automatically; open it to post depreciation. Define
          <RouterLink to="/m/asset-category" class="text-blue-600 hover:underline">Asset Categories</RouterLink>
          (method + accounts) and
          <RouterLink to="/m/location" class="text-blue-600 hover:underline">Locations</RouterLink> first.
        </p>
      </div>
      <div class="flex gap-2">
        <RouterLink to="/asset-capitalize" class="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50">
          Capitalize
        </RouterLink>
        <button class="btn-primary" @click="showForm = !showForm">
          {{ showForm ? "Close" : "New Asset" }}
        </button>
      </div>
    </div>

    <form v-if="showForm" class="mb-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm" @submit.prevent="save">
      <div class="grid grid-cols-2 gap-4 md:grid-cols-3">
        <div>
          <label class="form-label">Asset name*</label>
          <input v-model="fName" type="text" required class="form-input" placeholder="e.g. Forklift #1" />
        </div>
        <div>
          <label class="form-label">Category*</label>
          <select v-model="fCategory" required class="form-input">
            <option value="" disabled>Select…</option>
            <option v-for="c in categories" :key="c.id" :value="c.id">
              {{ c.category_name }} ({{ c.depreciation_method }})
            </option>
          </select>
        </div>
        <div>
          <label class="form-label">Location</label>
          <select v-model="fLocation" class="form-input">
            <option value="">—</option>
            <option v-for="l in locations" :key="l.id" :value="l.id">{{ l.location_name }}</option>
          </select>
        </div>
        <div>
          <label class="form-label">Gross purchase amount*</label>
          <input v-model.number="fGross" type="number" min="0" step="any" required class="form-input" />
        </div>
        <div>
          <label class="form-label">Custodian</label>
          <input v-model="fCustodian" type="text" class="form-input" placeholder="who holds it" />
        </div>
        <div>
          <label class="form-label">Opening accumulated depreciation</label>
          <input v-model.number="fOpening" type="number" min="0" step="any" class="form-input" />
        </div>
        <div>
          <label class="form-label">Purchase date</label>
          <input v-model="fPurchaseDate" type="date" class="form-input" />
        </div>
        <div>
          <label class="form-label">Available for use*</label>
          <input v-model="fInUseDate" type="date" required class="form-input" />
        </div>
        <div class="md:col-span-3">
          <label class="form-label">Remarks</label>
          <input v-model="fRemarks" type="text" class="form-input" />
        </div>
      </div>
      <p class="mt-2 text-xs text-gray-500">
        Depreciation starts from the <strong>available-for-use date</strong>. The schedule (number of
        entries, frequency, salvage, accounts) comes from the chosen category. You can preview it on the
        next screen before submitting.
      </p>
      <p v-if="!categories.length" class="mt-1 text-xs text-amber-600">
        No asset categories yet — create one under Asset Category first.
      </p>
      <p v-if="error" class="mt-2 text-sm text-red-600">{{ error.detail }}</p>
      <div class="mt-4 flex justify-end">
        <button type="submit" class="btn-primary" :disabled="saving || !fName || !fCategory || !fGross">
          {{ saving ? "Saving…" : "Create draft" }}
        </button>
      </div>
    </form>

    <div class="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      <table class="min-w-full text-sm">
        <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
          <tr>
            <th class="px-4 py-2">Asset</th><th class="px-4 py-2">Category</th>
            <th class="px-4 py-2">Location</th>
            <th class="px-4 py-2 text-right">Cost</th>
            <th class="px-4 py-2 text-right">Accumulated Dep.</th>
            <th class="px-4 py-2 text-right">Book Value</th>
            <th class="px-4 py-2">Status</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.id"
            class="cursor-pointer border-t border-gray-100 hover:bg-gray-50"
            @click="router.push(`/assets/${row.id}`)"
          >
            <td class="px-4 py-1.5">
              <div class="font-medium text-gray-900">{{ row.asset_name }}</div>
              <div class="text-xs text-gray-400">{{ row.name }}</div>
            </td>
            <td class="px-4 py-1.5">{{ row.category_name ?? "—" }}</td>
            <td class="px-4 py-1.5 text-gray-500">{{ row.location_name ?? "—" }}</td>
            <td class="px-4 py-1.5 text-right">{{ formatCurrency(row.gross_purchase_amount) }}</td>
            <td class="px-4 py-1.5 text-right text-gray-500">{{ formatCurrency(row.accumulated_depreciation) }}</td>
            <td class="px-4 py-1.5 text-right font-medium">{{ formatCurrency(row.book_value) }}</td>
            <td class="px-4 py-1.5"><StatusBadge :status="row.status" /></td>
          </tr>
          <tr v-if="!rows.length && !loading">
            <td colspan="7" class="px-4 py-8 text-center text-gray-400">
              No assets yet. Register one to start tracking depreciation.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
