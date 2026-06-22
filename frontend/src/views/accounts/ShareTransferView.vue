<script setup lang="ts">
// Share Transfers: Issue (mint), Transfer (holder→holder) or Buyback (retire) shares.
// No GL — this is the cap-table register. Holdings are derived from submitted transfers,
// so the live cap table lives under Reports → Cap Table. Submit validates the seller's balance.
import { computed, onMounted, ref } from "vue";
import { api } from "@/api/client";
import { formatDate } from "@/utils/format";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import type { ErrorEnvelope, ListResponse } from "@/types/core";

interface TransferRow {
  id: string;
  name: string;
  transfer_type: string;
  share_type_name: string | null;
  from_shareholder_name: string | null;
  to_shareholder_name: string | null;
  no_of_shares: number;
  transfer_date: string;
  status: string;
}
interface ShareTypeOpt { id: string; share_type_name: string }
interface ShareholderOpt { id: string; shareholder_name: string }

type TransferType = "Issue" | "Transfer" | "Buyback";

const rows = ref<TransferRow[]>([]);
const shareTypes = ref<ShareTypeOpt[]>([]);
const shareholders = ref<ShareholderOpt[]>([]);
const loading = ref(false);
const error = ref<ErrorEnvelope | null>(null);

const showForm = ref(false);
const today = new Date().toISOString().slice(0, 10);
const fType = ref<TransferType>("Issue");
const fShareType = ref("");
const fFrom = ref("");
const fTo = ref("");
const fShares = ref<number | null>(null);
const fRate = ref<number>(0);
const fDate = ref(today);
const saving = ref(false);

// Issue needs only "to"; Buyback only "from"; Transfer both.
const needsFrom = computed(() => fType.value !== "Issue");
const needsTo = computed(() => fType.value !== "Buyback");

async function fetchOptions(): Promise<void> {
  const [st, sh] = await Promise.all([
    api.get<ListResponse<ShareTypeOpt>>("/registry/share-type", { params: { page_size: 200 } }),
    api.get<ListResponse<ShareholderOpt>>("/registry/shareholder", { params: { page_size: 200 } }),
  ]);
  shareTypes.value = st.data.items;
  shareholders.value = sh.data.items;
}

async function fetchList(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    rows.value = (
      await api.get<ListResponse<TransferRow>>("/share-transfers", { params: { page_size: 100 } })
    ).data.items;
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    loading.value = false;
  }
}

async function save(): Promise<void> {
  if (!fShareType.value || !fShares.value) return;
  saving.value = true;
  error.value = null;
  try {
    await api.post("/share-transfers", {
      transfer_type: fType.value,
      share_type_id: fShareType.value,
      from_shareholder_id: needsFrom.value ? fFrom.value || null : null,
      to_shareholder_id: needsTo.value ? fTo.value || null : null,
      no_of_shares: fShares.value,
      rate: fRate.value || 0,
      transfer_date: fDate.value,
    });
    showForm.value = false;
    fShareType.value = "";
    fFrom.value = "";
    fTo.value = "";
    fShares.value = null;
    fRate.value = 0;
    await fetchList();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    saving.value = false;
  }
}

async function act(row: TransferRow, action: "submit" | "cancel"): Promise<void> {
  error.value = null;
  try {
    await api.post(`/share-transfers/${row.id}/${action}`);
    await fetchList();
  } catch (e) {
    error.value = e as ErrorEnvelope;
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
        <h1 class="text-xl font-semibold text-gray-900">Share Transfers</h1>
        <p class="text-sm text-gray-500">
          Issue, transfer or buy back shares. This is the cap-table register — no ledger posting. See live
          holdings under <RouterLink to="/reports?tab=share-balance" class="text-blue-600 hover:underline">Cap Table</RouterLink>;
          define <RouterLink to="/m/share-type" class="text-blue-600 hover:underline">Share Types</RouterLink> and
          <RouterLink to="/m/shareholder" class="text-blue-600 hover:underline">Shareholders</RouterLink> first.
        </p>
      </div>
      <button class="btn-primary" @click="showForm = !showForm">
        {{ showForm ? "Close" : "New Transfer" }}
      </button>
    </div>

    <form v-if="showForm" class="mb-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm" @submit.prevent="save">
      <div class="grid grid-cols-2 gap-4 md:grid-cols-3">
        <div>
          <label class="form-label">Type*</label>
          <select v-model="fType" class="form-input">
            <option value="Issue">Issue (mint new)</option>
            <option value="Transfer">Transfer (holder → holder)</option>
            <option value="Buyback">Buyback (retire)</option>
          </select>
        </div>
        <div>
          <label class="form-label">Share Type*</label>
          <select v-model="fShareType" required class="form-input">
            <option value="" disabled>Select…</option>
            <option v-for="s in shareTypes" :key="s.id" :value="s.id">{{ s.share_type_name }}</option>
          </select>
        </div>
        <div>
          <label class="form-label">Transfer date</label>
          <input v-model="fDate" type="date" class="form-input" />
        </div>
        <div v-if="needsFrom">
          <label class="form-label">From shareholder*</label>
          <select v-model="fFrom" class="form-input">
            <option value="" disabled>Select…</option>
            <option v-for="h in shareholders" :key="h.id" :value="h.id">{{ h.shareholder_name }}</option>
          </select>
        </div>
        <div v-if="needsTo">
          <label class="form-label">To shareholder*</label>
          <select v-model="fTo" class="form-input">
            <option value="" disabled>Select…</option>
            <option v-for="h in shareholders" :key="h.id" :value="h.id">{{ h.shareholder_name }}</option>
          </select>
        </div>
        <div>
          <label class="form-label">No. of shares*</label>
          <input v-model.number="fShares" type="number" min="1" step="1" required class="form-input" />
        </div>
        <div>
          <label class="form-label">Rate (per share)</label>
          <input v-model.number="fRate" type="number" min="0" step="any" class="form-input" />
        </div>
      </div>
      <p class="mt-2 text-xs text-gray-500">
        Holdings take effect on <strong>submit</strong>, which checks the seller owns enough shares. Cancelling
        a submitted transfer reverses it automatically (balances are derived, not stored).
      </p>
      <p v-if="error" class="mt-2 text-sm text-red-600">{{ error.detail }}</p>
      <div class="mt-4 flex justify-end">
        <button type="submit" class="btn-primary" :disabled="saving || !fShareType || !fShares">
          {{ saving ? "Saving…" : "Create draft" }}
        </button>
      </div>
    </form>

    <div class="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      <table class="min-w-full text-sm">
        <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
          <tr>
            <th class="px-4 py-2">Transfer</th><th class="px-4 py-2">Type</th>
            <th class="px-4 py-2">Share Type</th><th class="px-4 py-2">From → To</th>
            <th class="px-4 py-2 text-right">Shares</th><th class="px-4 py-2">Date</th>
            <th class="px-4 py-2">Status</th><th class="px-4 py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id" class="border-t border-gray-100">
            <td class="px-4 py-1.5 font-medium text-gray-900">{{ row.name }}</td>
            <td class="px-4 py-1.5">{{ row.transfer_type }}</td>
            <td class="px-4 py-1.5">{{ row.share_type_name ?? "—" }}</td>
            <td class="px-4 py-1.5 text-gray-500">
              {{ row.from_shareholder_name ?? "—" }} → {{ row.to_shareholder_name ?? "—" }}
            </td>
            <td class="px-4 py-1.5 text-right">{{ row.no_of_shares }}</td>
            <td class="px-4 py-1.5 text-gray-500">{{ formatDate(row.transfer_date) }}</td>
            <td class="px-4 py-1.5"><StatusBadge :status="row.status" /></td>
            <td class="px-4 py-1.5">
              <div class="flex flex-wrap items-center gap-2">
                <button v-if="row.status === 'Draft'" class="text-xs text-green-700 hover:underline"
                        @click="act(row, 'submit')">submit</button>
                <button v-if="row.status === 'Submitted'" class="text-xs text-red-600 hover:underline"
                        @click="act(row, 'cancel')">cancel</button>
              </div>
            </td>
          </tr>
          <tr v-if="!rows.length && !loading">
            <td colspan="8" class="px-4 py-8 text-center text-gray-400">
              No share transfers yet. Issue shares to a shareholder to start the cap table.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
