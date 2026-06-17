<script setup lang="ts">
// Standalone Delivery Note create form (ERPNext-style). The list + detail live
// in FulfilmentView; this is the "New Delivery Note" authoring screen. A DN
// created here is not tied to a Sales Order (the SO → DN flow stays on the SO
// screen). No taxes/discount on a DN — just lines with per-row warehouse.

import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import ItemsGrid, { type GridColumn } from "@/components/shared/ItemsGrid.vue";
import DataEntry, { type ImportedRow } from "@/components/shared/DataEntry.vue";
import DateField from "@/components/shared/DateField.vue";
import CurrencySection, { type CurrencyModel } from "@/components/shared/CurrencySection.vue";
import { rowKey } from "@/utils/rowKey";
import { useAccountsStore } from "@/stores/accounts";
import { useStockStore } from "@/stores/stock";
import { useCoreStore } from "@/stores/core";
import { useAuthStore } from "@/stores/auth";
import { api } from "@/api/client";
import type { ErrorEnvelope } from "@/types/core";

interface DnItemIn {
  item_id: string;
  qty: number;
  rate: number | null;
  uom?: string;
  warehouse_id?: string | null;
  _rowKey?: string;
}

const router = useRouter();
const accounts = useAccountsStore();
const stock = useStockStore();
const core = useCoreStore();
const auth = useAuthStore();
if (!core.companies.length) void core.fetchCompanies();

const error = ref<ErrorEnvelope | null>(null);
const saving = ref(false);

const partyId = ref("");
const postingDate = ref(new Date().toISOString().slice(0, 10));
const setWarehouseId = ref("");
const remarks = ref("");
const currencyModel = ref<CurrencyModel>({ currency: "", conversion_rate: 1 });
const items = ref<DnItemIn[]>([{ item_id: "", qty: 1, rate: null, uom: "", _rowKey: rowKey() } as DnItemIn]);

const activeTab = ref("Details");
const tabs = ["Details", "Address & Contact", "Terms", "More Info"];

const activeCompany = computed(() => core.companies.find((c) => c.id === auth.companyId));
const companyName = computed(() => activeCompany.value?.company_name ?? "");
const companyCurrency = computed(() => activeCompany.value?.default_currency ?? "INR");

const warehouseOptions = computed(() =>
  stock.leafWarehouses.map((w) => ({ value: w.id, label: w.warehouse_name })),
);

const gridColumns = computed<GridColumn[]>(() => [
  { key: "item_id", label: "Item / Service", type: "item", required: true },
  { key: "qty", label: "Quantity", type: "number", align: "right", required: true },
  { key: "uom", label: "UOM", type: "text" },
  { key: "rate", label: "Rate", type: "number", align: "right" },
  { key: "warehouse_id", label: "Warehouse", type: "select", options: warehouseOptions.value },
]);

const gridRows = computed<Record<string, unknown>[]>({
  get: () => items.value as unknown as Record<string, unknown>[],
  set: (rows) => {
    items.value = rows as unknown as DnItemIn[];
  },
});

function newItemRow(): Record<string, unknown> {
  return { item_id: "", qty: 1, rate: null, uom: "", _rowKey: rowKey() };
}

async function onItemChange(index: number): Promise<void> {
  const row = items.value[index];
  if (!row?.item_id) return;
  const item = stock.items.find((it) => it.id === row.item_id);
  let rate: number | null = row.rate ?? null;
  try {
    const resolved = await stock.resolveItemRate(row.item_id, false);
    rate = Number(resolved.rate);
  } catch {
    // best-effort; backend re-resolves on save
  }
  items.value = items.value.map((r, i) =>
    i === index ? { ...r, rate, uom: item?.stock_uom ?? r.uom } : r,
  );
}

function applyImportedRows(rows: ImportedRow[]): void {
  const additions: DnItemIn[] = [];
  for (const r of rows) {
    const item = stock.items.find((it) => it.item_code.toLowerCase() === r.item_code.toLowerCase());
    if (!item) continue;
    additions.push({
      item_id: item.id,
      qty: Number(r.qty) || 1,
      rate: r.rate != null ? Number(r.rate) : Number(item.standard_rate) || null,
      uom: item.stock_uom,
      _rowKey: rowKey(),
    });
  }
  if (additions.length) {
    items.value = [...items.value.filter((i) => i.item_id || Number(i.rate)), ...additions];
  }
}

async function save(): Promise<void> {
  saving.value = true;
  error.value = null;
  try {
    const payload: Record<string, unknown> = {
      customer_id: partyId.value,
      posting_date: postingDate.value,
      currency: currencyModel.value.currency || null,
      conversion_rate: currencyModel.value.conversion_rate || 1,
      set_warehouse_id: setWarehouseId.value || null,
      remarks: remarks.value || null,
      items: items.value
        .filter((i) => i.item_id)
        .map((i) => ({
          item_id: i.item_id,
          qty: i.qty,
          rate: i.rate ?? 0,
          uom: i.uom || null,
          warehouse_id: i.warehouse_id || null,
        })),
    };
    const resp = await api.post<{ id: string }>("/delivery-notes", payload);
    void router.push(`/delivery-notes/${resp.data.id}`);
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  await Promise.all([accounts.fetchCustomers(), stock.fetchItems(), stock.fetchWarehouses()]);
});
</script>

<template>
  <form @submit.prevent="save">
    <!-- top bar -->
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
      <nav class="flex flex-wrap items-center gap-2 text-sm text-gray-500">
        <span>Stock</span><span class="text-gray-300">/</span>
        <span>Delivery Note</span><span class="text-gray-300">/</span>
        <span class="font-semibold text-gray-900">New Delivery Note</span>
        <span class="ml-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
          Not Saved
        </span>
      </nav>
      <button type="submit" class="btn-primary" :disabled="saving || !partyId">
        {{ saving ? "Saving…" : "Save" }}
      </button>
    </div>

    <!-- tabs -->
    <div class="mb-6 border-b border-gray-200">
      <nav class="flex gap-6">
        <button
          v-for="tab in tabs"
          :key="tab"
          type="button"
          class="-mb-px border-b-2 px-1 pb-2 text-sm font-medium"
          :class="activeTab === tab ? 'border-primary text-primary' : 'border-transparent text-gray-500 hover:text-gray-700'"
          @click="activeTab = tab"
        >
          {{ tab }}
        </button>
      </nav>
    </div>

    <div v-show="activeTab === 'Details'" class="space-y-8">
      <!-- header fields -->
      <div class="grid grid-cols-1 gap-x-8 gap-y-4 md:grid-cols-3">
        <div>
          <label class="form-label">Series</label>
          <div class="form-input bg-gray-50 text-gray-600">MAT-DN-.YYYY.-</div>
        </div>
        <div>
          <label class="form-label">Posting Date <span class="text-red-500">*</span></label>
          <DateField v-model="postingDate" required />
        </div>
        <div>
          <label class="form-label">Customer <span class="text-red-500">*</span></label>
          <select v-model="partyId" required class="form-input">
            <option value="" disabled>Select…</option>
            <option v-for="c in accounts.customers" :key="c.id" :value="c.id">{{ c.customer_name }}</option>
          </select>
        </div>
        <div>
          <label class="form-label">Company</label>
          <div class="form-input bg-gray-50 text-gray-600">{{ companyName || "—" }}</div>
        </div>
        <div>
          <label class="form-label">Set Source Warehouse</label>
          <select v-model="setWarehouseId" class="form-input">
            <option value="">—</option>
            <option v-for="w in stock.leafWarehouses" :key="w.id" :value="w.id">{{ w.warehouse_name }}</option>
          </select>
        </div>
      </div>

      <!-- items -->
      <div>
        <div class="mb-2 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-gray-900">Items &amp; Services</h2>
          <DataEntry @import="applyImportedRows" />
        </div>
        <ItemsGrid
          v-model="gridRows"
          :columns="gridColumns"
          :item-options="stock.itemOptions"
          :currency="currencyModel.currency || companyCurrency"
          :new-row="newItemRow"
          @item-change="onItemChange"
        />
        <p class="mt-2 text-xs text-gray-400">
          Each line ships from its own warehouse (or the Set Source Warehouse / item default).
        </p>
      </div>

      <!-- currency -->
      <CurrencySection v-model="currencyModel" :company-currency="companyCurrency" />

      <!-- remarks -->
      <div>
        <label class="form-label">Remarks</label>
        <input v-model="remarks" class="form-input" placeholder="Optional note" />
      </div>

      <p v-if="error" class="text-sm text-red-600">
        {{ error.detail }}<span v-if="error.field" class="text-gray-400"> ({{ error.field }})</span>
      </p>
      <div class="flex justify-end">
        <button type="button" class="btn-secondary" @click="router.push('/delivery-notes')">Cancel</button>
      </div>
    </div>

    <div
      v-show="activeTab !== 'Details'"
      class="rounded-lg border border-dashed border-gray-300 bg-white p-10 text-center text-sm text-gray-400"
    >
      This section isn’t built yet.
    </div>
  </form>
</template>
