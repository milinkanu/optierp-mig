<script setup lang="ts">
// Standalone Purchase Receipt create form (ERPNext-style). List + detail live in
// FulfilmentView; this is the "New Purchase Receipt" authoring screen. A PR
// created here is ad-hoc (the PO → PR flow stays on the PO screen via "Create
// Receipt"). No taxes/discount on a PR — just received lines with per-row
// warehouse. (Accepted/rejected-qty split is a backend follow-up.)

import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import ItemsGrid, { type GridColumn } from "@/components/shared/ItemsGrid.vue";
import GetItemsFrom, { type ItemSource } from "@/components/shared/GetItemsFrom.vue";
import DataEntry, { type ImportedRow } from "@/components/shared/DataEntry.vue";
import DateField from "@/components/shared/DateField.vue";
import CurrencySection, { type CurrencyModel } from "@/components/shared/CurrencySection.vue";
import { rowKey } from "@/utils/rowKey";
import { useAccountsStore } from "@/stores/accounts";
import { useStockStore } from "@/stores/stock";
import { useCoreStore } from "@/stores/core";
import { useAuthStore } from "@/stores/auth";
import { api } from "@/api/client";
import type { ErrorEnvelope, ListResponse } from "@/types/core";
import type { OrderDetail } from "@/types/trade";
import type { FulfilmentDetail, FulfilmentListItem } from "@/types/stock";

interface PrItemIn {
  item_id: string;
  qty: number;
  rate: number | null;
  uom?: string;
  warehouse_id?: string | null;
  rejected_qty?: number;
  rejected_warehouse_id?: string | null;
  purchase_order_item_id?: string | null;
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

// Stock-qty display for the grid: blank for plain stock-UOM lines, else qty × factor
function stockQtyLabel(row: Record<string, unknown>): string {
  const f = stock.uomFactor(row.item_id as string, row.uom as string | undefined);
  if (f === 1) return "";
  return String(Math.round((Number(row.qty) || 0) * f * 1000) / 1000);
}

interface ChargeIn {
  description: string;
  account_id: string;
  amount: number | null;
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
const supplierDeliveryNote = ref("");
const returnables = ref<FulfilmentListItem[]>([]); // submitted, non-return receipts
const charges = ref<ChargeIn[]>([]); // landed cost (freight/customs/insurance)
const currencyModel = ref<CurrencyModel>({ currency: "", conversion_rate: 1 });

function addCharge(): void {
  charges.value.push({ description: "", account_id: "", amount: null });
}
function removeCharge(i: number): void {
  charges.value.splice(i, 1);
}
const items = ref<PrItemIn[]>([{ item_id: "", qty: 1, rate: null, uom: "", _rowKey: rowKey() } as PrItemIn]);

const activeTab = ref("Details");
const tabs = ["Details", "Address & Contact", "Terms", "More Info"];

const activeCompany = computed(() => core.companies.find((c) => c.id === auth.companyId));
const companyName = computed(() => activeCompany.value?.company_name ?? "");
const companyCurrency = computed(() => activeCompany.value?.default_currency ?? "INR");

const warehouseOptions = computed(() =>
  stock.leafWarehouses.map((w) => ({ value: w.id, label: w.warehouse_name })),
);

const sources: ItemSource[] = [
  { label: "Purchase Order", param: "purchase_order_id", endpoint: "/purchase-orders" },
];

// Pull unreceived lines from a Purchase Order, carrying purchase_order_item_id so
// the PR accrues received_qty on the PO (mirrors the PO-screen "Create Receipt").
async function prefillFromPurchaseOrder(poId: string): Promise<void> {
  error.value = null;
  try {
    const po = (await api.get<OrderDetail>(`/purchase-orders/${poId}`)).data;
    partyId.value = po.supplier_id ?? "";
    const pending = po.items
      .map((r) => ({ r, qty: Number(r.qty) - (Number(r.received_qty) || 0) }))
      .filter(({ qty }) => qty > 0.000001)
      .map(({ r, qty }) => ({
        item_id: r.item_id ?? "",
        qty: Math.round(qty * 1000) / 1000,
        rate: Number(r.rate),
        uom: r.uom ?? "",
        warehouse_id: r.warehouse_id ?? setWarehouseId.value ?? null,
        purchase_order_item_id: r.id,
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
  if (param === "purchase_order_id") void prefillFromPurchaseOrder(id);
}

// Returns: list submitted, non-return receipts to pick a return-against; on
// pick, prefill the lines (the user trims qty down to the returned amount).
// Carries purchase_order_item_id so the PO received_qty nets back.
async function fetchReturnables(): Promise<void> {
  try {
    const resp = await api.get<ListResponse<FulfilmentListItem>>("/purchase-receipts", {
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
    const orig = (await api.get<FulfilmentDetail>(`/purchase-receipts/${id}`)).data;
    isReturn.value = true;
    returnAgainstId.value = id;
    partyId.value = orig.supplier_id ?? "";
    const rows = orig.items.map((r) => ({
      item_id: r.item_id,
      qty: Number(r.qty),
      rate: Number(r.rate),
      uom: r.uom ?? "",
      warehouse_id: r.warehouse_id ?? null,
      purchase_order_item_id: r.purchase_order_item_id ?? null,
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

const gridColumns = computed<GridColumn[]>(() => [
  { key: "item_id", label: "Item / Service", type: "item", required: true },
  { key: "qty", label: isReturn.value ? "Quantity" : "Accepted Qty", type: "number", align: "right", required: true },
  { key: "uom", label: "UOM", type: "select", optionsKey: "_uomOptions" },
  { key: "stock_qty", label: "Stock Qty", type: "computed", align: "right", compute: stockQtyLabel },
  { key: "serial_nos", label: "Serials", type: "serials", showIfKey: "_serialized", requiredFor: requiredSerials },
  { key: "batch_no", label: "Batch", type: "select", optionsKey: "_batchOptions", showIfKey: "_batched" },
  { key: "rate", label: "Rate", type: "number", align: "right" },
  { key: "warehouse_id", label: "Warehouse", type: "select", options: warehouseOptions.value },
  // rejected split is only meaningful on a real receipt, not a return
  ...(isReturn.value
    ? []
    : [
        { key: "rejected_qty", label: "Rejected Qty", type: "number", align: "right" } as GridColumn,
        { key: "rejected_warehouse_id", label: "Rejected WH", type: "select", options: warehouseOptions.value } as GridColumn,
      ]),
]);

const gridRows = computed<Record<string, unknown>[]>({
  get: () => items.value as unknown as Record<string, unknown>[],
  set: (rows) => {
    items.value = rows as unknown as PrItemIn[];
  },
});

function newItemRow(): Record<string, unknown> {
  return {
    item_id: "", qty: 1, rate: null, uom: "", rejected_qty: 0, rejected_warehouse_id: null,
    serial_nos: "", _serialized: false, batch_no: null, _batched: false, _batchOptions: [],
    _uomOptions: [], _rowKey: rowKey(),
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
  // default to the item's purchase UOM (buying); rate is per that UOM
  const uom = item?.purchase_uom || item?.stock_uom || "";
  const factor = stock.uomFactor(row.item_id, uom);
  let rate: number | null = row.rate ?? null;
  try {
    const resolved = await stock.resolveItemRate(row.item_id, true);
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
  const additions: PrItemIn[] = [];
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
  // Mirror the backend contract client-side so the user gets a friendly message
  // instead of a raw 422: at least one line, each with a positive quantity
  // (PurchaseReceiptItemIn.qty is gt=0; PurchaseReceiptCreate.items min_length=1).
  const validItems = items.value.filter((i) => i.item_id && Number(i.qty) > 0);
  if (validItems.length === 0) {
    error.value = { detail: "Add at least one item with a quantity greater than zero." } as ErrorEnvelope;
    return;
  }
  saving.value = true;
  error.value = null;
  try {
    const payload: Record<string, unknown> = {
      supplier_id: partyId.value,
      posting_date: postingDate.value,
      currency: currencyModel.value.currency || null,
      conversion_rate: currencyModel.value.conversion_rate || 1,
      set_warehouse_id: setWarehouseId.value || null,
      is_return: isReturn.value,
      return_against_id: isReturn.value ? returnAgainstId.value || null : null,
      supplier_delivery_note: supplierDeliveryNote.value || null,
      remarks: remarks.value || null,
      charges: isReturn.value
        ? []
        : charges.value
            .filter((c) => c.account_id && Number(c.amount) > 0)
            .map((c) => ({
              description: c.description || "Charge",
              account_id: c.account_id,
              amount: c.amount ?? 0,
            })),
      items: validItems.map((i) => ({
        item_id: i.item_id,
        qty: i.qty,
        rate: i.rate ?? 0,
        uom: i.uom || null,
        warehouse_id: i.warehouse_id || null,
        rejected_qty: i.rejected_qty ?? 0,
        rejected_warehouse_id: i.rejected_warehouse_id || null,
        serial_nos: i.serial_nos
          ? i.serial_nos.split("\n").map((s) => s.trim()).filter(Boolean)
          : null,
        batch_no: i.batch_no || null,
        purchase_order_item_id: i.purchase_order_item_id || null,
      })),
    };
    const resp = await api.post<{ id: string }>("/purchase-receipts", payload);
    void router.push(`/purchase-receipts/${resp.data.id}`);
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  await Promise.all([
    accounts.fetchSuppliers(), accounts.fetchAccounts(),
    stock.fetchItems(), stock.fetchWarehouses(), fetchReturnables(),
  ]);
  const fromPo = route.query.purchase_order_id;
  if (typeof fromPo === "string") await prefillFromPurchaseOrder(fromPo);
  const retAgainst = route.query.return_against;
  if (typeof retAgainst === "string") await prefillFromReturn(retAgainst);
});
</script>

<template>
  <form @submit.prevent="save">
    <!-- top bar -->
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
      <nav class="flex flex-wrap items-center gap-2 text-sm text-gray-500">
        <span>Purchases</span><span class="text-gray-300">/</span>
        <span>Purchase Receipt</span><span class="text-gray-300">/</span>
        <span class="font-semibold text-gray-900">{{ isReturn ? "New Purchase Return" : "New Purchase Receipt" }}</span>
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
          <div class="form-input bg-gray-50 text-gray-600">MAT-PRE-.YYYY.-</div>
        </div>
        <div>
          <label class="form-label">Posting Date <span class="text-red-500">*</span></label>
          <DateField v-model="postingDate" required />
        </div>
        <div>
          <label class="form-label">Supplier <span class="text-red-500">*</span></label>
          <select v-model="partyId" required class="form-input">
            <option value="" disabled>Select…</option>
            <option v-for="s in accounts.suppliers" :key="s.id" :value="s.id">{{ s.supplier_name }}</option>
          </select>
        </div>
        <div>
          <label class="form-label">Company</label>
          <div class="form-input bg-gray-50 text-gray-600">{{ companyName || "—" }}</div>
        </div>
        <div>
          <label class="form-label">Set Target Warehouse</label>
          <select v-model="setWarehouseId" class="form-input">
            <option value="">—</option>
            <option v-for="w in stock.leafWarehouses" :key="w.id" :value="w.id">{{ w.warehouse_name }}</option>
          </select>
        </div>
        <div>
          <label class="form-label">Supplier Delivery Note</label>
          <input v-model="supplierDeliveryNote" class="form-input" placeholder="Supplier's DN ref (optional)" />
        </div>
        <div class="flex items-end pb-2">
          <label class="flex items-center gap-2 text-sm text-gray-700">
            <input v-model="isReturn" type="checkbox" class="rounded border-gray-300" />
            Is Return (Purchase Return)
          </label>
        </div>
        <div v-if="isReturn" class="md:col-span-2">
          <label class="form-label">Return Against <span class="text-red-500">*</span></label>
          <select v-model="returnAgainstId" class="form-input" @change="onReturnAgainstChange">
            <option value="">Select original receipt…</option>
            <option v-for="d in returnables" :key="d.id" :value="d.id">
              {{ d.name }}<template v-if="d.supplier_name"> — {{ d.supplier_name }}</template>
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
          Each line is received into its own warehouse (or the Set Target Warehouse / item default).
        </p>
      </div>

      <!-- additional costs (landed cost) -->
      <div v-if="!isReturn">
        <div class="mb-2 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-gray-900">Additional Costs (Landed Cost)</h2>
          <button type="button" class="btn-secondary text-xs" @click="addCharge">+ Add charge</button>
        </div>
        <table v-if="charges.length" class="min-w-full text-sm">
          <thead class="text-left text-xs uppercase text-gray-500">
            <tr>
              <th class="py-1 pr-3">Description</th>
              <th class="py-1 pr-3">Account</th>
              <th class="py-1 pr-3 text-right">Amount</th>
              <th class="py-1"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(c, i) in charges" :key="i" class="border-t border-gray-100">
              <td class="py-1 pr-3">
                <input v-model="c.description" class="form-input" placeholder="Freight / Customs / Insurance" />
              </td>
              <td class="py-1 pr-3">
                <select v-model="c.account_id" class="form-input">
                  <option value="">Select account…</option>
                  <option v-for="a in accounts.accountOptions" :key="a.value" :value="a.value">{{ a.label }}</option>
                </select>
              </td>
              <td class="py-1 pr-3">
                <input v-model.number="c.amount" type="number" step="any" class="form-input text-right" />
              </td>
              <td class="py-1 text-right">
                <button type="button" class="text-gray-400 hover:text-red-600" @click="removeCharge(i)">✕</button>
              </td>
            </tr>
          </tbody>
        </table>
        <p class="mt-2 text-xs text-gray-400">
          Charges are apportioned by item value into the incoming stock valuation on submit
          (no separate Landed Cost Voucher). Pick a clearing/expense account per row.
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
        <button type="button" class="btn-secondary" @click="router.push('/purchase-receipts')">Cancel</button>
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
