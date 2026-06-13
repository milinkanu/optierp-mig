<script setup lang="ts">
// Shared create/detail view for Quotations / Sales Orders / Purchase Orders,
// with the document-flow actions (convert, fulfil, bill).

import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import { useAccountsStore } from "@/stores/accounts";
import { useStockStore } from "@/stores/stock";
import { api } from "@/api/client";
import { formatCurrency, formatDate, formatNumber, formatQty } from "@/utils/format";
import type { ErrorEnvelope } from "@/types/core";
import type { OrderDetail, OrderItemIn } from "@/types/trade";
import type { OrderKind } from "@/views/trade/OrderListView.vue";

const props = defineProps<{ kind: OrderKind; id?: string }>();
const router = useRouter();
const route = useRoute();
const accounts = useAccountsStore();
const stock = useStockStore();

const CONFIG = {
  quotation: { endpoint: "/quotations", title: "Quotation", party: "Customer", buying: false },
  "sales-order": { endpoint: "/sales-orders", title: "Sales Order", party: "Customer", buying: false },
  "purchase-order": { endpoint: "/purchase-orders", title: "Purchase Order", party: "Supplier", buying: true },
} as const;

const cfg = computed(() => CONFIG[props.kind]);
const parties = computed(() => (cfg.value.buying ? accounts.suppliers : accounts.customers));

const doc = ref<OrderDetail | null>(null);
const error = ref<ErrorEnvelope | null>(null);
const warnings = ref<string[]>([]);
const saving = ref(false);

const partyId = ref("");
const postingDate = ref(new Date().toISOString().slice(0, 10));
const extraDate = ref(""); // delivery_date (SO) / schedule_date (PO) / valid_till (QTN)
const remarks = ref("");
const items = ref<OrderItemIn[]>([{ item_id: "", qty: 1, rate: null }]);
const quotationId = ref<string | null>(null);
const supplierQuotationId = ref<string | null>(null);

const extraDateLabel = computed(() =>
  props.kind === "sales-order" ? "Delivery Date"
  : props.kind === "purchase-order" ? "Expected Receipt"
  : "Valid Till",
);

const previewNet = computed(() =>
  items.value.reduce((sum, i) => sum + (Number(i.qty) || 0) * (Number(i.rate) || 0), 0),
);

const money = (value: string | number | null | undefined): string =>
  formatCurrency(value, doc.value?.currency ?? "INR");

const docPartyName = computed(() => doc.value?.customer_name ?? doc.value?.supplier_name ?? "");

// fulfilment dialog (Create Delivery Note / Purchase Receipt)
const showFulfil = ref(false);
const fulfilQty = ref<Record<string, number>>({});

const pendingRows = computed(() => {
  if (!doc.value) return [];
  return doc.value.items.filter((row) => {
    const done = Number(props.kind === "sales-order" ? row.delivered_qty : row.received_qty) || 0;
    return Number(row.qty) - done > 0.000001;
  });
});

function pendingOf(row: OrderDetail["items"][number]): number {
  const done = Number(props.kind === "sales-order" ? row.delivered_qty : row.received_qty) || 0;
  return Number(row.qty) - done;
}

function openFulfil(): void {
  fulfilQty.value = {};
  for (const row of pendingRows.value) fulfilQty.value[row.id] = pendingOf(row);
  showFulfil.value = true;
}

async function createFulfilment(): Promise<void> {
  if (!doc.value) return;
  error.value = null;
  const isSO = props.kind === "sales-order";
  const lines = pendingRows.value
    .filter((row) => (fulfilQty.value[row.id] || 0) > 0)
    .map((row) => ({
      item_id: row.item_id,
      qty: fulfilQty.value[row.id],
      warehouse_id: row.warehouse_id ?? null,
      ...(isSO ? { sales_order_item_id: row.id } : { purchase_order_item_id: row.id }),
    }));
  if (!lines.length) return;
  try {
    const endpoint = isSO ? "/delivery-notes" : "/purchase-receipts";
    const payload: Record<string, unknown> = { posting_date: new Date().toISOString().slice(0, 10), items: lines };
    if (isSO) payload.customer_id = doc.value.customer_id;
    else payload.supplier_id = doc.value.supplier_id;
    const resp = await api.post<{ id: string }>(endpoint, payload);
    void router.push(`${endpoint}/${resp.data.id}`);
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

function createInvoice(): void {
  if (!doc.value) return;
  if (props.kind === "sales-order") {
    void router.push({ name: "sales-invoice-new", query: { sales_order_id: doc.value.id } });
  } else {
    void router.push({ name: "purchase-invoice-new", query: { purchase_order_id: doc.value.id } });
  }
}

function createSalesOrder(): void {
  if (!doc.value) return;
  void router.push({ name: "sales-order-new", query: { quotation_id: doc.value.id } });
}

async function pickItem(row: OrderItemIn): Promise<void> {
  if (!row.item_id) return;
  try {
    const rate = await stock.resolveItemRate(row.item_id, cfg.value.buying);
    // switching items always refreshes the rate — keeping the previous
    // item's price silently misprices the line
    row.rate = Number(rate.rate);
  } catch {
    // rate resolution is best-effort; the backend re-resolves on save
  }
}

async function save(): Promise<void> {
  saving.value = true;
  error.value = null;
  try {
    const payload: Record<string, unknown> = {
      posting_date: postingDate.value,
      remarks: remarks.value || null,
      items: items.value.filter((i) => i.item_id),
    };
    if (props.kind === "sales-order") {
      payload.customer_id = partyId.value;
      payload.delivery_date = extraDate.value || null;
      if (quotationId.value) payload.quotation_id = quotationId.value;
    } else if (props.kind === "purchase-order") {
      payload.supplier_id = partyId.value;
      payload.schedule_date = extraDate.value || null;
      if (supplierQuotationId.value) payload.supplier_quotation_id = supplierQuotationId.value;
    } else {
      payload.customer_id = partyId.value;
      payload.valid_till = extraDate.value || null;
    }
    const resp = await api.post<OrderDetail>(cfg.value.endpoint, payload);
    void router.push(`${cfg.value.endpoint}/${resp.data.id}`);
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    saving.value = false;
  }
}

async function action(name: "submit" | "cancel"): Promise<void> {
  if (!doc.value) return;
  error.value = null;
  try {
    const resp = await api.post<OrderDetail>(`${cfg.value.endpoint}/${doc.value.id}/${name}`);
    doc.value = resp.data;
    warnings.value = resp.data.warnings ?? [];
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

async function prefill(): Promise<void> {
  // Sales Order from a Quotation
  const fromQuotation = route.query.quotation_id;
  if (props.kind === "sales-order" && typeof fromQuotation === "string") {
    const quotation = (await api.get<OrderDetail>(`/quotations/${fromQuotation}`)).data;
    partyId.value = quotation.customer_id ?? "";
    quotationId.value = quotation.id;
    items.value = quotation.items.map((row) => ({
      item_id: row.item_id ?? "",
      qty: Number(row.qty),
      rate: Number(row.rate),
      quotation_item_id: row.id,
    }));
    return;
  }
  // Purchase Order from a Supplier Quotation
  const fromSq = route.query.supplier_quotation_id;
  if (props.kind === "purchase-order" && typeof fromSq === "string") {
    const sq = (await api.get<OrderDetail>(`/supplier-quotations/${fromSq}`)).data;
    partyId.value = sq.supplier_id ?? "";
    supplierQuotationId.value = sq.id;
    items.value = sq.items.map((row) => ({
      item_id: row.item_id ?? "",
      qty: Number(row.qty),
      rate: Number(row.rate),
    }));
    return;
  }
  // Purchase Order from a Material Request
  const fromMr = route.query.material_request_id;
  if (props.kind === "purchase-order" && typeof fromMr === "string") {
    const mr = (await api.get<{ items: Array<{ id: string; item_id: string; qty: string; ordered_qty: string }> }>(
      `/material-requests/${fromMr}`,
    )).data;
    items.value = mr.items
      .filter((row) => Number(row.qty) - Number(row.ordered_qty) > 0)
      .map((row) => ({
        item_id: row.item_id,
        qty: Number(row.qty) - Number(row.ordered_qty),
        rate: null,
        material_request_item_id: row.id,
      }));
    for (const row of items.value) await pickItem(row);
  }
}

onMounted(async () => {
  await Promise.all([
    cfg.value.buying ? accounts.fetchSuppliers() : accounts.fetchCustomers(),
    stock.fetchItems(),
    stock.fetchWarehouses(),
  ]);
  if (props.id) {
    doc.value = (await api.get<OrderDetail>(`${cfg.value.endpoint}/${props.id}`)).data;
  } else {
    await prefill();
  }
});
</script>

<template>
  <div class="max-w-5xl">
    <!-- detail -->
    <div v-if="doc">
      <div class="mb-4 flex items-center justify-between">
        <div>
          <h1 class="text-xl font-semibold text-gray-900">{{ docPartyName || doc.name }}</h1>
          <p class="text-sm text-gray-500">{{ doc.name }}</p>
        </div>
        <div class="flex items-center gap-3">
          <StatusBadge :status="doc.status" />
          <button v-if="doc.docstatus === 0" class="btn-primary" @click="action('submit')">Submit</button>
          <button v-if="kind === 'quotation' && doc.status === 'Open'" class="btn-primary"
                  @click="createSalesOrder">Create Sales Order</button>
          <button v-if="kind !== 'quotation' && doc.docstatus === 1 && pendingRows.length"
                  class="btn-primary" @click="openFulfil">
            {{ kind === "sales-order" ? "Create Delivery Note" : "Create Receipt" }}
          </button>
          <button v-if="kind !== 'quotation' && doc.docstatus === 1 && Number(doc.per_billed) < 99.999"
                  class="btn-secondary" @click="createInvoice">Create Invoice</button>
          <button v-if="doc.docstatus === 1" class="btn-secondary" @click="action('cancel')">Cancel</button>
        </div>
      </div>
      <p v-if="error" class="mb-3 text-sm text-red-600">{{ error.detail }}</p>
      <div v-if="warnings.length" class="mb-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
        <p v-for="w in warnings" :key="w">⚠ {{ w }}</p>
      </div>

      <!-- fulfilment dialog -->
      <div v-if="showFulfil" class="mb-4 rounded-lg border border-primary/30 bg-white p-5 shadow-sm">
        <h2 class="mb-2 text-sm font-semibold text-gray-900">
          {{ kind === "sales-order" ? "Deliver pending items" : "Receive pending items" }}
        </h2>
        <div v-for="row in pendingRows" :key="row.id" class="mb-1 grid grid-cols-12 items-center gap-2 text-sm">
          <span class="col-span-6 font-medium text-gray-900">{{ row.item_name }}</span>
          <span class="col-span-3 text-gray-500">pending {{ formatQty(String(pendingOf(row))) }}</span>
          <input v-model.number="fulfilQty[row.id]" type="number" min="0" :max="pendingOf(row)" step="any"
                 class="form-input col-span-3" />
        </div>
        <div class="mt-3 flex justify-end gap-2">
          <button class="btn-secondary" @click="showFulfil = false">Close</button>
          <button class="btn-primary" @click="createFulfilment">Create Draft</button>
        </div>
      </div>

      <div class="mb-4 grid grid-cols-2 gap-x-8 gap-y-3 rounded-lg border border-gray-200 bg-white p-5 shadow-sm md:grid-cols-4">
        <div>
          <div class="text-xs font-semibold uppercase tracking-wide text-gray-400">{{ cfg.party }}</div>
          <div class="mt-0.5 text-sm font-medium text-gray-900">{{ docPartyName || "—" }}</div>
        </div>
        <div>
          <div class="text-xs font-semibold uppercase tracking-wide text-gray-400">Date</div>
          <div class="mt-0.5 text-sm text-gray-900">{{ formatDate(doc.posting_date) }}</div>
        </div>
        <div>
          <div class="text-xs font-semibold uppercase tracking-wide text-gray-400">{{ extraDateLabel }}</div>
          <div class="mt-0.5 text-sm text-gray-900">
            {{ formatDate(doc.delivery_date ?? doc.schedule_date ?? doc.valid_till ?? null) }}
          </div>
        </div>
        <div>
          <div class="text-xs font-semibold uppercase tracking-wide text-gray-400">Currency</div>
          <div class="mt-0.5 text-sm text-gray-900">{{ doc.currency }}</div>
        </div>
        <div v-if="kind !== 'quotation'" class="col-span-2 grid grid-cols-2 gap-x-8 md:col-span-4 md:grid-cols-4">
          <div>
            <div class="text-xs font-semibold uppercase tracking-wide text-gray-400">
              {{ kind === "sales-order" ? "Delivered" : "Received" }}
            </div>
            <div class="mt-0.5 text-sm text-gray-900">
              {{ formatQty(doc.per_delivered ?? doc.per_received ?? "0") }}%
            </div>
          </div>
          <div>
            <div class="text-xs font-semibold uppercase tracking-wide text-gray-400">Billed</div>
            <div class="mt-0.5 text-sm text-gray-900">{{ formatQty(doc.per_billed ?? "0") }}%</div>
          </div>
        </div>
        <div v-if="doc.remarks" class="col-span-2 md:col-span-4">
          <div class="text-xs font-semibold uppercase tracking-wide text-gray-400">Remarks</div>
          <div class="mt-0.5 text-sm text-gray-700">{{ doc.remarks }}</div>
        </div>
      </div>

      <div class="rounded-lg border border-gray-200 bg-white shadow-sm">
        <table class="min-w-full text-sm">
          <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th class="px-4 py-2">#</th><th class="px-4 py-2">Item</th>
              <th class="px-4 py-2 text-right">Qty</th>
              <th v-if="kind !== 'quotation'" class="px-4 py-2 text-right">
                {{ kind === "sales-order" ? "Delivered" : "Received" }}
              </th>
              <th class="px-4 py-2 text-right">Rate</th>
              <th class="px-4 py-2 text-right">Amount</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in doc.items" :key="item.idx" class="border-t border-gray-100">
              <td class="px-4 py-2">{{ item.idx }}</td>
              <td class="px-4 py-2 font-medium text-gray-900">
                {{ item.item_code ? `${item.item_code} — ` : "" }}{{ item.item_name }}
              </td>
              <td class="px-4 py-2 text-right">{{ formatQty(item.qty) }}</td>
              <td v-if="kind !== 'quotation'" class="px-4 py-2 text-right">
                {{ formatQty(item.delivered_qty ?? item.received_qty ?? "0") }}
              </td>
              <td class="px-4 py-2 text-right">{{ money(item.rate) }}</td>
              <td class="px-4 py-2 text-right">{{ money(item.amount) }}</td>
            </tr>
          </tbody>
        </table>
        <div class="border-t border-gray-200 p-4">
          <dl class="ml-auto w-80 space-y-1 text-sm">
            <div class="flex justify-between"><dt class="text-gray-500">Net Total</dt><dd>{{ money(doc.net_total) }}</dd></div>
            <div v-for="tax in doc.taxes" :key="tax.idx" class="flex justify-between">
              <dt class="text-gray-500">{{ tax.description || tax.charge_type }}
                <template v-if="Number(tax.rate)">({{ Number(tax.rate) }}%)</template></dt>
              <dd>{{ money(tax.tax_amount) }}</dd>
            </div>
            <div v-if="Number(doc.discount_amount)" class="flex justify-between text-gray-500">
              <dt>Discount</dt><dd>-{{ money(doc.discount_amount) }}</dd>
            </div>
            <div class="flex justify-between border-t border-gray-200 pt-1 text-base font-semibold">
              <dt>Grand Total</dt><dd>{{ money(doc.rounded_total) }}</dd>
            </div>
          </dl>
        </div>
      </div>
    </div>

    <!-- new document form -->
    <form v-else class="space-y-4" @submit.prevent="save">
      <h1 class="text-xl font-semibold text-gray-900">New {{ cfg.title }}</h1>
      <div class="grid grid-cols-3 gap-4 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <div>
          <label class="form-label">{{ cfg.party }}*</label>
          <select v-model="partyId" required class="form-input">
            <option value="" disabled>Select…</option>
            <option v-for="p in parties" :key="p.id" :value="p.id">
              {{ "customer_name" in p ? p.customer_name : p.supplier_name }}
            </option>
          </select>
        </div>
        <div>
          <label class="form-label">Date*</label>
          <input v-model="postingDate" type="date" required class="form-input" />
        </div>
        <div>
          <label class="form-label">{{ extraDateLabel }}</label>
          <input v-model="extraDate" type="date" class="form-input" />
        </div>
      </div>

      <div class="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <div class="mb-2 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-gray-900">Items</h2>
          <button type="button" class="btn-secondary" @click="items.push({ item_id: '', qty: 1, rate: null })">
            Add Row
          </button>
        </div>
        <div v-for="(item, i) in items" :key="i" class="mb-2 grid grid-cols-12 gap-2">
          <select v-model="item.item_id" class="form-input col-span-6" @change="pickItem(item)">
            <option value="" disabled>Item…</option>
            <option v-for="opt in stock.itemOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
          <input v-model.number="item.qty" type="number" step="any" min="0" placeholder="Qty" class="form-input col-span-2" />
          <input v-model.number="item.rate" type="number" step="any" min="0" placeholder="Rate (auto)" class="form-input col-span-2" />
          <div class="col-span-2 flex items-center justify-end pr-2 text-sm text-gray-600">
            {{ formatNumber((item.qty || 0) * (Number(item.rate) || 0)) }}
          </div>
        </div>
        <p class="text-right text-sm font-medium text-gray-700">Net: {{ formatNumber(previewNet) }}</p>
        <p class="mt-1 text-right text-xs text-gray-400">
          Taxes resolve from the {{ cfg.party.toLowerCase() }}'s tax category on save.
        </p>
      </div>

      <div class="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <label class="form-label">Remarks</label>
        <input v-model="remarks" class="form-input" placeholder="Optional note" />
      </div>

      <p v-if="error" class="text-sm text-red-600">
        {{ error.detail }}<span v-if="error.field" class="text-gray-400"> ({{ error.field }})</span>
      </p>
      <div class="flex justify-end gap-3">
        <button type="button" class="btn-secondary" @click="router.back()">Cancel</button>
        <button type="submit" class="btn-primary" :disabled="saving || !partyId">
          {{ saving ? "Saving…" : "Save Draft" }}
        </button>
      </div>
    </form>
  </div>
</template>
