<script setup lang="ts">
// Stock reports: balance (per item/warehouse) and movement ledger.

import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "@/api/client";
import { useStockStore } from "@/stores/stock";
import { useCompanyCurrency } from "@/composables/useCompanyCurrency";
import { formatCurrency, formatDate, formatQty } from "@/utils/format";
import type { ErrorEnvelope } from "@/types/core";
import type { StockAgeingRow, StockBalanceRow, StockLedgerRow } from "@/types/stock";

type StockTab = "balance" | "ledger" | "ageing";

const store = useStockStore();
const companyCurrency = useCompanyCurrency();
const route = useRoute();
const router = useRouter();

function tabFromQuery(t: unknown): StockTab {
  return t === "ledger" || t === "ageing" ? t : "balance";
}

const tab = ref<StockTab>(tabFromQuery(route.query.tab));
const warehouseId = ref("");
const itemId = ref("");
const asOf = ref(""); // empty = current; a date = historical / ageing as-of
const balanceRows = ref<StockBalanceRow[]>([]);
const ledgerRows = ref<StockLedgerRow[]>([]);
const ageingRows = ref<StockAgeingRow[]>([]);
const loading = ref(false);
const error = ref<ErrorEnvelope | null>(null);

async function run(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const params: Record<string, string> = {};
    if (warehouseId.value) params.warehouse_id = warehouseId.value;
    if (itemId.value) params.item_id = itemId.value;
    if (tab.value === "balance") {
      balanceRows.value = []; // avoid flashing the prior tab's rows during the fetch
      if (asOf.value) params.as_of = asOf.value;
      balanceRows.value = (await api.get<StockBalanceRow[]>("/reports/stock-balance", { params })).data;
    } else if (tab.value === "ageing") {
      ageingRows.value = [];
      if (asOf.value) params.as_of = asOf.value;
      ageingRows.value = (await api.get<StockAgeingRow[]>("/reports/stock-ageing", { params })).data;
    } else {
      ledgerRows.value = [];
      ledgerRows.value = (await api.get<StockLedgerRow[]>("/reports/stock-ledger", { params })).data;
    }
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    loading.value = false;
  }
}

// the URL is the source of truth for the tab: in-page buttons push the query,
// the watcher below applies it — so sidebar ?tab= links never become dead links
function switchTab(next: StockTab): void {
  if (next !== tabFromQuery(route.query.tab)) {
    void router.push({ query: { ...route.query, tab: next } });
  }
}

// single responder to URL tab changes (in-page buttons + sidebar links)
watch(
  () => route.query.tab,
  (t) => {
    tab.value = tabFromQuery(t);
    void run();
  },
);

onMounted(async () => {
  await Promise.all([store.fetchItems(), store.fetchWarehouses()]);
  await run();
});
</script>

<template>
  <div>
    <div class="mb-4 flex items-center justify-between">
      <h1 class="text-xl font-semibold text-gray-900">Stock</h1>
      <div class="flex items-center gap-3">
        <input v-if="tab !== 'ledger'" v-model="asOf" type="date" class="form-input w-40"
               title="As of date (leave blank for today / current)" @change="run" />
        <select v-model="itemId" class="form-input w-56" @change="run">
          <option value="">All items</option>
          <option v-for="opt in store.itemOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <select v-model="warehouseId" class="form-input w-48" @change="run">
          <option value="">All warehouses</option>
          <option v-for="w in store.leafWarehouses" :key="w.id" :value="w.id">{{ w.warehouse_name }}</option>
        </select>
      </div>
    </div>

    <div class="mb-4 flex gap-1 border-b border-gray-200">
      <button v-for="t in (['balance', 'ledger', 'ageing'] as const)" :key="t"
              class="border-b-2 px-4 py-2 text-sm font-medium"
              :class="tab === t ? 'border-primary text-primary' : 'border-transparent text-gray-500 hover:text-gray-700'"
              @click="switchTab(t)">
        {{ t === "balance" ? "Stock Balance" : t === "ledger" ? "Stock Ledger" : "Stock Ageing" }}
      </button>
    </div>
    <p v-if="tab !== 'ledger' && asOf" class="mb-2 text-xs text-gray-400">
      Historical snapshot as of {{ formatDate(asOf) }} — on-hand only.
    </p>
    <p v-if="error" class="mb-2 text-sm text-red-600">{{ error.detail }}</p>

    <div class="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      <table v-if="tab === 'balance'" class="min-w-full text-sm">
        <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
          <tr>
            <th class="px-4 py-2">Item</th><th class="px-4 py-2">Warehouse</th>
            <th class="px-4 py-2 text-right">In Stock</th>
            <th class="px-4 py-2 text-right">Reserved</th>
            <th class="px-4 py-2 text-right">Ordered</th>
            <th class="px-4 py-2 text-right">Projected</th>
            <th class="px-4 py-2 text-right">Valuation</th>
            <th class="px-4 py-2 text-right">Stock Value</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in balanceRows" :key="i" class="border-t border-gray-100">
            <td class="px-4 py-2 font-medium text-gray-900">{{ row.item_code }} — {{ row.item_name }}</td>
            <td class="px-4 py-2 text-gray-500">{{ row.warehouse_name }}</td>
            <td class="px-4 py-2 text-right">{{ formatQty(row.actual_qty) }}</td>
            <td class="px-4 py-2 text-right text-amber-700">{{ formatQty(row.reserved_qty) }}</td>
            <td class="px-4 py-2 text-right text-blue-700">{{ formatQty(row.ordered_qty) }}</td>
            <td class="px-4 py-2 text-right">{{ formatQty(row.projected_qty) }}</td>
            <td class="px-4 py-2 text-right">{{ formatCurrency(row.valuation_rate, companyCurrency) }}</td>
            <td class="px-4 py-2 text-right font-medium">{{ formatCurrency(row.stock_value, companyCurrency) }}</td>
          </tr>
          <tr v-if="!loading && !balanceRows.length">
            <td colspan="8" class="px-4 py-8 text-center text-gray-400">No stock yet — post a Purchase Receipt or Stock Entry.</td>
          </tr>
        </tbody>
      </table>

      <table v-else-if="tab === 'ledger'" class="min-w-full text-sm">
        <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
          <tr>
            <th class="px-4 py-2">Date</th><th class="px-4 py-2">Item</th>
            <th class="px-4 py-2">Warehouse</th><th class="px-4 py-2">Voucher</th>
            <th class="px-4 py-2 text-right">Qty</th>
            <th class="px-4 py-2 text-right">Balance Qty</th>
            <th class="px-4 py-2 text-right">Valuation</th>
            <th class="px-4 py-2 text-right">Value Change</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in ledgerRows" :key="i" class="border-t border-gray-100">
            <td class="px-4 py-2 text-gray-500">{{ formatDate(row.posting_date) }}</td>
            <td class="px-4 py-2 font-medium text-gray-900">{{ row.item_code }}</td>
            <td class="px-4 py-2 text-gray-500">{{ row.warehouse_name }}</td>
            <td class="px-4 py-2">{{ row.voucher_no }}</td>
            <td class="px-4 py-2 text-right"
                :class="Number(row.actual_qty) >= 0 ? 'text-green-700' : 'text-red-700'">
              {{ formatQty(row.actual_qty) }}
            </td>
            <td class="px-4 py-2 text-right">{{ formatQty(row.qty_after_transaction) }}</td>
            <td class="px-4 py-2 text-right">{{ formatCurrency(row.valuation_rate, companyCurrency) }}</td>
            <td class="px-4 py-2 text-right">{{ formatCurrency(row.stock_value_difference, companyCurrency) }}</td>
          </tr>
          <tr v-if="!loading && !ledgerRows.length">
            <td colspan="8" class="px-4 py-8 text-center text-gray-400">No stock movements yet.</td>
          </tr>
        </tbody>
      </table>

      <table v-else class="min-w-full text-sm">
        <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
          <tr>
            <th class="px-4 py-2">Item</th><th class="px-4 py-2">Warehouse</th>
            <th class="px-4 py-2 text-right">On Hand</th>
            <th class="px-4 py-2 text-right">Avg Age (days)</th>
            <th class="px-4 py-2 text-right">0–30</th>
            <th class="px-4 py-2 text-right">31–60</th>
            <th class="px-4 py-2 text-right">61–90</th>
            <th class="px-4 py-2 text-right">90+</th>
            <th class="px-4 py-2 text-right">Stock Value</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in ageingRows" :key="i" class="border-t border-gray-100">
            <td class="px-4 py-2 font-medium text-gray-900">{{ row.item_code }} — {{ row.item_name }}</td>
            <td class="px-4 py-2 text-gray-500">{{ row.warehouse_name }}</td>
            <td class="px-4 py-2 text-right">{{ formatQty(row.total_qty) }}</td>
            <td class="px-4 py-2 text-right">{{ row.average_age_days }}</td>
            <td class="px-4 py-2 text-right">{{ formatQty(row.bucket_0_30) }}</td>
            <td class="px-4 py-2 text-right">{{ formatQty(row.bucket_31_60) }}</td>
            <td class="px-4 py-2 text-right">{{ formatQty(row.bucket_61_90) }}</td>
            <td class="px-4 py-2 text-right" :class="Number(row.bucket_90_plus) > 0 ? 'text-amber-700 font-medium' : ''">
              {{ formatQty(row.bucket_90_plus) }}
            </td>
            <td class="px-4 py-2 text-right font-medium">{{ formatCurrency(row.stock_value, companyCurrency) }}</td>
          </tr>
          <tr v-if="!loading && !ageingRows.length">
            <td colspan="9" class="px-4 py-8 text-center text-gray-400">No on-hand stock to age.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
