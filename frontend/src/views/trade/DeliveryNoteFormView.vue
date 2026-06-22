<script setup lang="ts">
// Standalone Delivery Note create form (ERPNext-style). The list + detail live
// in FulfilmentView; this is the "New Delivery Note" authoring screen. A DN
// created here is not tied to a Sales Order (the SO → DN flow stays on the SO
// screen). No taxes/discount on a DN — just lines with per-row warehouse.

import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import ItemsGrid, { type GridColumn } from "@/components/shared/ItemsGrid.vue";
import GetItemsFrom, { type ItemSource } from "@/components/shared/GetItemsFrom.vue";
import DataEntry, { type ImportedRow } from "@/components/shared/DataEntry.vue";
import DateField from "@/components/shared/DateField.vue";
import CurrencySection, { type CurrencyModel } from "@/components/shared/CurrencySection.vue";
import AddressContactTab, { type AddressContactModel } from "@/components/shared/AddressContactTab.vue";
import { rowKey } from "@/utils/rowKey";
import { useAccountsStore } from "@/stores/accounts";
import { useStockStore } from "@/stores/stock";
import { useCoreStore } from "@/stores/core";
import { useAuthStore } from "@/stores/auth";
import { api } from "@/api/client";
import type { ErrorEnvelope, ListResponse } from "@/types/core";
import type { OrderDetail } from "@/types/trade";
import type { FulfilmentDetail, FulfilmentListItem } from "@/types/stock";

interface DnItemIn {
  item_id: string;
  qty: number;
  rate: number | null;
  uom?: string;
  warehouse_id?: string | null;
  sales_order_item_id?: string | null;
  serial_nos?: string; // newline-separated
  batch_no?: string | null; // lot label (batched items)
  _serialized?: boolean;
  _batched?: boolean;
  _batchOptions?: { value: string; label: string }[];
  _uomOptions?: { value: string; label: string }[];
  _rowKey?: string;
}

// Fetch a batched item's existing batches for the per-row dropdown.
async function loadBatchOptions(itemId: string): Promise<{ value: string; label: string }[]> {
  const { data } = await api.get<ListResponse<{ batch_no: string; expiry_date: string | null }>>(
    "/registry/batch",
    { params: { item_id: itemId, page_size: 200 } },
  );
  return data.items.map((b) => ({
    value: b.batch_no,
    label: b.expiry_date ? `${b.batch_no} (exp ${b.expiry_date})` : b.batch_no,
  }));
}

function requiredSerials(row: Record<string, unknown>): number {
  return (Number(row.qty) || 0) * stock.uomFactor(row.item_id as string, row.uom as string | undefined);
}

const router = useRouter();
const route = useRoute();
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
const isReturn = ref(false);
const returnAgainstId = ref("");
const returnables = ref<FulfilmentListItem[]>([]); // submitted, non-return DNs
const currencyModel = ref<CurrencyModel>({ currency: "", conversion_rate: 1 });
const items = ref<DnItemIn[]>([{ item_id: "", qty: 1, rate: null, uom: "", _rowKey: rowKey() } as DnItemIn]);
const addressContact = ref<AddressContactModel>({
  billing_address_id: null,
  shipping_address_id: null,
  contact_person_id: null,
});

// Map the generic A&C picks to the customer billing-address column.
function acPayload(): Record<string, unknown> {
  return {
    customer_address_id: addressContact.value.billing_address_id,
    shipping_address_id: addressContact.value.shipping_address_id,
    contact_person_id: addressContact.value.contact_person_id,
  };
}

const activeTab = ref("Details");
const tabs = ["Details", "Address & Contact", "Terms", "More Info"];

const activeCompany = computed(() => core.companies.find((c) => c.id === auth.companyId));
const companyName = computed(() => activeCompany.value?.company_name ?? "");
const companyCurrency = computed(() => activeCompany.value?.default_currency ?? "INR");

const warehouseOptions = computed(() =>
  stock.leafWarehouses.map((w) => ({ value: w.id, label: w.warehouse_name })),
);

const sources: ItemSource[] = [{ label: "Sales Order", param: "sales_order_id", endpoint: "/sales-orders" }];

// Pull undelivered lines from a Sales Order, carrying sales_order_item_id so the
// DN accrues delivered_qty on the SO (mirrors the SO-screen "Create Delivery Note").
async function prefillFromSalesOrder(soId: string): Promise<void> {
  error.value = null;
  try {
    const so = (await api.get<OrderDetail>(`/sales-orders/${soId}`)).data;
    partyId.value = so.customer_id ?? "";
    const pending = so.items
      .map((r) => ({ r, qty: Number(r.qty) - (Number(r.delivered_qty) || 0) }))
      .filter(({ qty }) => qty > 0.000001)
      .map(({ r, qty }) => ({
        item_id: r.item_id ?? "",
        qty: Math.round(qty * 1000) / 1000,
        rate: Number(r.rate),
        uom: r.uom ?? "",
        warehouse_id: r.warehouse_id ?? setWarehouseId.value ?? null,
        sales_order_item_id: r.id,
        serial_nos: "",
        _serialized: stock.items.find((it) => it.id === r.item_id)?.has_serial_no ?? false,
        batch_no: null,
        _batched: stock.items.find((it) => it.id === r.item_id)?.has_batch_no ?? false,
        _batchOptions: [],
        _uomOptions: stock.uomOptionsFor(r.item_id ?? ""),
        _rowKey: rowKey(),
      }));
    if (pending.length) {
      items.value = pending;
      await hydrateBatchOptions();
    }
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

function onGetItems(param: string, id: string): void {
  if (param === "sales_order_id") void prefillFromSalesOrder(id);
}

// Returns: list submitted, non-return deliveries to pick a return-against; on
// pick, prefill the lines from that delivery (the user trims qty down to the
// returned amount). Carries sales_order_item_id so the SO delivered_qty nets back.
async function fetchReturnables(): Promise<void> {
  try {
    const resp = await api.get<ListResponse<FulfilmentListItem>>("/delivery-notes", {
      params: { page_size: 100 },
    });
    returnables.value = resp.data.items.filter((d) => d.docstatus === 1 && !d.is_return);
  } catch {
    returnables.value = [];
  }
}

async function prefillFromReturn(id: string): Promise<void> {
  error.value = null;
  try {
    const orig = (await api.get<FulfilmentDetail>(`/delivery-notes/${id}`)).data;
    isReturn.value = true;
    returnAgainstId.value = id;
    partyId.value = orig.customer_id ?? "";
    const rows = orig.items.map((r) => ({
      item_id: r.item_id,
      qty: Number(r.qty),
      rate: Number(r.rate),
      uom: r.uom ?? "",
      warehouse_id: r.warehouse_id ?? null,
      sales_order_item_id: r.sales_order_item_id ?? null,
      serial_nos: r.serial_nos ?? "",
      _serialized: stock.items.find((it) => it.id === r.item_id)?.has_serial_no ?? false,
      batch_no: r.batch_no ?? null,
      _batched: stock.items.find((it) => it.id === r.item_id)?.has_batch_no ?? false,
      _batchOptions: [],
      _uomOptions: stock.uomOptionsFor(r.item_id),
      _rowKey: rowKey(),
    }));
    if (rows.length) {
      items.value = rows;
      await hydrateBatchOptions();
    }
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

function onReturnAgainstChange(): void {
  if (returnAgainstId.value) void prefillFromReturn(returnAgainstId.value);
}

// Stock-qty display: blank for plain stock-UOM lines, else qty × factor
function stockQtyLabel(row: Record<string, unknown>): string {
  const f = stock.uomFactor(row.item_id as string, row.uom as string | undefined);
  if (f === 1) return "";
  return String(Math.round((Number(row.qty) || 0) * f * 1000) / 1000);
}

const gridColumns = computed<GridColumn[]>(() => [
  { key: "item_id", label: "Item / Service", type: "item", required: true },
  { key: "qty", label: "Quantity", type: "number", align: "right", required: true },
  { key: "uom", label: "UOM", type: "select", optionsKey: "_uomOptions" },
  { key: "stock_qty", label: "Stock Qty", type: "computed", align: "right", compute: stockQtyLabel },
  { key: "serial_nos", label: "Serials", type: "serials", showIfKey: "_serialized", requiredFor: requiredSerials },
  { key: "batch_no", label: "Batch", type: "select", optionsKey: "_batchOptions", showIfKey: "_batched" },
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
  return {
    item_id: "", qty: 1, rate: null, uom: "", serial_nos: "", _serialized: false,
    batch_no: null, _batched: false, _batchOptions: [], _uomOptions: [], _rowKey: rowKey(),
  };
}

// Load the batches dropdown for any batched rows (used after a prefill where the
// rows are built synchronously).
async function hydrateBatchOptions(): Promise<void> {
  const updated = await Promise.all(
    items.value.map(async (r) =>
      r._batched && r.item_id ? { ...r, _batchOptions: await loadBatchOptions(r.item_id) } : r,
    ),
  );
  items.value = updated;
}

async function onItemChange(index: number): Promise<void> {
  const row = items.value[index];
  if (!row?.item_id) return;
  const item = stock.items.find((it) => it.id === row.item_id);
  // default to the item's sales UOM (selling); rate is per that UOM
  const uom = item?.sales_uom || item?.stock_uom || "";
  const factor = stock.uomFactor(row.item_id, uom);
  let rate: number | null = row.rate ?? null;
  try {
    const resolved = await stock.resolveItemRate(row.item_id, false);
    rate = Number(resolved.rate) * factor; // resolved is per stock UOM
  } catch {
    // best-effort; backend re-resolves on save
  }
  const batched = item?.has_batch_no ?? false;
  const batchOptions = batched ? await loadBatchOptions(row.item_id) : [];
  items.value = items.value.map((r, i) =>
    i === index
      ? { ...r, rate, uom, _serialized: item?.has_serial_no ?? false,
          _batched: batched, _batchOptions: batchOptions, batch_no: null,
          _uomOptions: stock.uomOptionsFor(row.item_id) }
      : r,
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
      serial_nos: "",
      _serialized: item.has_serial_no,
      batch_no: null,
      _batched: item.has_batch_no,
      _batchOptions: [],
      _uomOptions: stock.uomOptionsFor(item.id),
      _rowKey: rowKey(),
    });
  }
  if (additions.length) {
    items.value = [...items.value.filter((i) => i.item_id || Number(i.rate)), ...additions];
    void hydrateBatchOptions();
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
      is_return: isReturn.value,
      return_against_id: isReturn.value ? returnAgainstId.value || null : null,
      ...acPayload(),
      remarks: remarks.value || null,
      items: items.value
        .filter((i) => i.item_id)
        .map((i) => ({
          item_id: i.item_id,
          qty: i.qty,
          rate: i.rate ?? 0,
          uom: i.uom || null,
          warehouse_id: i.warehouse_id || null,
          serial_nos: i.serial_nos
            ? i.serial_nos.split("\n").map((s) => s.trim()).filter(Boolean)
            : null,
          batch_no: i.batch_no || null,
          sales_order_item_id: i.sales_order_item_id || null,
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
  await Promise.all([
    accounts.fetchCustomers(), stock.fetchItems(), stock.fetchWarehouses(), fetchReturnables(),
  ]);
  const fromSo = route.query.sales_order_id;
  if (typeof fromSo === "string") await prefillFromSalesOrder(fromSo);
  const retAgainst = route.query.return_against;
  if (typeof retAgainst === "string") await prefillFromReturn(retAgainst);
});
</script>

<template>
  <form @submit.prevent="save">
    <!-- top bar -->
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
      <nav class="flex flex-wrap items-center gap-2 text-sm text-gray-500">
        <span>Inventory</span><span class="text-gray-300">/</span>
        <span>Delivery Note</span><span class="text-gray-300">/</span>
        <span class="font-semibold text-gray-900">{{ isReturn ? "New Sales Return" : "New Delivery Note" }}</span>
        <span class="ml-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
          Not Saved
        </span>
      </nav>
      <div class="flex items-center gap-2">
        <GetItemsFrom :sources="sources" @select="onGetItems" />
        <button type="submit" class="btn-primary" :disabled="saving || !partyId || (isReturn && !returnAgainstId)">
          {{ saving ? "Saving…" : "Save" }}
        </button>
      </div>
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
        <div class="flex items-end pb-2">
          <label class="flex items-center gap-2 text-sm text-gray-700">
            <input v-model="isReturn" type="checkbox" class="rounded border-gray-300" />
            Is Return (Sales Return)
          </label>
        </div>
        <div v-if="isReturn" class="md:col-span-2">
          <label class="form-label">Return Against <span class="text-red-500">*</span></label>
          <select v-model="returnAgainstId" class="form-input" @change="onReturnAgainstChange">
            <option value="">Select original delivery…</option>
            <option v-for="d in returnables" :key="d.id" :value="d.id">
              {{ d.name }}<template v-if="d.customer_name"> — {{ d.customer_name }}</template>
            </option>
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

    <div v-show="activeTab === 'Address & Contact'">
      <AddressContactTab v-model="addressContact" :party-id="partyId" party-kind="customer" />
    </div>

    <div
      v-show="activeTab !== 'Details' && activeTab !== 'Address & Contact'"
      class="rounded-lg border border-dashed border-gray-300 bg-white p-10 text-center text-sm text-gray-400"
    >
      This section isn’t built yet.
    </div>
  </form>
</template>
