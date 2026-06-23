<script setup lang="ts">
// Capitalize a new asset from costed components: each component credits a source account
// (CWIP, stock, labour, bank…) and the total is debited to the category's Fixed Asset
// account. Produces a live, depreciating asset.
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client";
import { formatCurrency } from "@/utils/format";
import type { ErrorEnvelope, ListResponse } from "@/types/core";

interface CategoryOpt { id: string; category_name: string }
interface LocationOpt { id: string; location_name: string }
interface AccountOpt { value: string; label: string }

const router = useRouter();
const categories = ref<CategoryOpt[]>([]);
const locations = ref<LocationOpt[]>([]);
const accounts = ref<AccountOpt[]>([]);
const error = ref<ErrorEnvelope | null>(null);
const saving = ref(false);

const today = new Date().toISOString().slice(0, 10);
const fName = ref("");
const fCategory = ref("");
const fLocation = ref("");
const fCustodian = ref("");
const fPostingDate = ref(today);
const fInUse = ref(today);
const components = ref<{ description: string; amount: number | null; account_id: string }[]>([
  { description: "", amount: null, account_id: "" },
]);

const total = computed(() => components.value.reduce((s, c) => s + (Number(c.amount) || 0), 0));

function addRow(): void {
  components.value.push({ description: "", amount: null, account_id: "" });
}
function removeRow(i: number): void {
  components.value.splice(i, 1);
  if (!components.value.length) addRow();
}

async function save(): Promise<void> {
  const rows = components.value.filter((c) => c.amount && c.account_id);
  if (!fName.value || !fCategory.value || !rows.length) return;
  saving.value = true;
  error.value = null;
  try {
    const created = (
      await api.post<{ id: string }>("/assets/capitalize", {
        asset_name: fName.value,
        asset_category_id: fCategory.value,
        location_id: fLocation.value || null,
        custodian: fCustodian.value || null,
        posting_date: fPostingDate.value,
        available_for_use_date: fInUse.value,
        components: rows.map((c) => ({
          description: c.description, amount: c.amount, account_id: c.account_id,
        })),
      })
    ).data;
    void router.push(`/assets/${created.id}`);
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  const [cat, loc, acc] = await Promise.all([
    api.get<ListResponse<CategoryOpt>>("/registry/asset-category", { params: { page_size: 200 } }),
    api.get<ListResponse<LocationOpt>>("/registry/location", { params: { page_size: 200 } }),
    api.get<AccountOpt[]>("/registry/account/options"),
  ]);
  categories.value = cat.data.items;
  locations.value = loc.data.items;
  accounts.value = acc.data;
});
</script>

<template>
  <div class="mx-auto max-w-4xl">
    <RouterLink to="/assets" class="text-sm text-blue-600 hover:underline">← Assets</RouterLink>
    <h1 class="mt-1 mb-1 text-xl font-semibold text-gray-900">Capitalize Asset</h1>
    <p class="mb-4 text-sm text-gray-500">
      Build a fixed asset from its costs — each line credits a source account (Capital Work in Progress,
      Stock In Hand for consumed parts, a labour/expense account, Bank…); the total is debited to the
      category's Fixed Asset account. The asset is created live and starts depreciating.
    </p>

    <p v-if="error" class="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-600">{{ error.detail }}</p>

    <form class="rounded-lg border border-gray-200 bg-white p-5 shadow-sm" @submit.prevent="save">
      <div class="grid grid-cols-2 gap-4 md:grid-cols-3">
        <div>
          <label class="form-label">Asset name*</label>
          <input v-model="fName" type="text" required class="form-input" placeholder="e.g. Cold Storage Unit" />
        </div>
        <div>
          <label class="form-label">Category*</label>
          <select v-model="fCategory" required class="form-input">
            <option value="" disabled>Select…</option>
            <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.category_name }}</option>
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
          <label class="form-label">Custodian</label>
          <input v-model="fCustodian" type="text" class="form-input" />
        </div>
        <div>
          <label class="form-label">Posting date*</label>
          <input v-model="fPostingDate" type="date" required class="form-input" />
        </div>
        <div>
          <label class="form-label">Available for use*</label>
          <input v-model="fInUse" type="date" required class="form-input" />
        </div>
      </div>

      <div class="mt-5">
        <label class="form-label">Cost components*</label>
        <div v-for="(c, i) in components" :key="i" class="mb-2 flex items-center gap-2">
          <input v-model="c.description" type="text" class="form-input flex-1" placeholder="e.g. Compressor unit" />
          <select v-model="c.account_id" class="form-input flex-1">
            <option value="" disabled>Source account…</option>
            <option v-for="a in accounts" :key="a.value" :value="a.value">{{ a.label }}</option>
          </select>
          <input v-model.number="c.amount" type="number" min="0" step="any" class="form-input w-32 text-right" placeholder="Amount" />
          <button type="button" class="text-sm text-red-600 hover:underline" @click="removeRow(i)">remove</button>
        </div>
        <button type="button" class="text-sm text-blue-600 hover:underline" @click="addRow">+ add component</button>
      </div>

      <div class="mt-4 flex items-center justify-between border-t border-gray-100 pt-4">
        <div class="text-sm">
          <span class="text-gray-500">Asset value (total):</span>
          <span class="ml-2 text-lg font-semibold text-gray-900">{{ formatCurrency(total) }}</span>
        </div>
        <button type="submit" class="btn-primary" :disabled="saving || !fName || !fCategory || total <= 0">
          {{ saving ? "Capitalizing…" : "Capitalize asset" }}
        </button>
      </div>
    </form>
  </div>
</template>
