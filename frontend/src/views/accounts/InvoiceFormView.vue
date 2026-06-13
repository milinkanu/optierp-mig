<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import { useAccountsStore } from "@/stores/accounts";
import { useCompanyCurrency } from "@/composables/useCompanyCurrency";
import { api, openPdf } from "@/api/client";
import { formatCurrency, formatDate, formatNumber, formatQty } from "@/utils/format";
import type { ErrorEnvelope } from "@/types/core";
import type {
  InvoiceDetail,
  InvoiceItemIn,
  PurchaseInvoiceDetail,
  SalesInvoiceDetail,
  TaxRowIn,
} from "@/types/accounts";

const props = defineProps<{ kind: "sales" | "purchase"; id?: string }>();
const router = useRouter();
const route = useRoute();
const store = useAccountsStore();
const companyCurrency = useCompanyCurrency();

const endpoint = computed(() => (props.kind === "sales" ? "/sales-invoices" : "/purchase-invoices"));
const partyLabel = computed(() => (props.kind === "sales" ? "Customer" : "Supplier"));
const parties = computed(() => (props.kind === "sales" ? store.customers : store.suppliers));

const docPartyName = computed(() => {
  if (!doc.value) return "";
  return props.kind === "sales"
    ? ((doc.value as SalesInvoiceDetail).customer_name ?? "")
    : ((doc.value as PurchaseInvoiceDetail).supplier_name ?? "");
});
const docBillNo = computed(() =>
  props.kind === "purchase" ? (doc.value as PurchaseInvoiceDetail | null)?.bill_no : null,
);
const money = (value: string | number | null | undefined): string =>
  formatCurrency(value, doc.value?.currency ?? "INR");

const doc = ref<InvoiceDetail | null>(null);
const error = ref<ErrorEnvelope | null>(null);
const saving = ref(false);

const partyId = ref("");
const newPartyName = ref("");
const postingDate = ref(new Date().toISOString().slice(0, 10));
const dueDate = ref("");
const items = ref<InvoiceItemIn[]>([{ item_name: "", qty: 1, rate: 0 }]);
const taxes = ref<TaxRowIn[]>([]);

const previewNet = computed(() =>
  items.value.reduce((sum, i) => sum + (Number(i.qty) || 0) * (Number(i.rate) || 0), 0),
);

function addItem(): void {
  items.value.push({ item_name: "", qty: 1, rate: 0 });
}

function addTax(): void {
  taxes.value.push({ charge_type: "On Net Total", rate: 0, account_head_id: "" });
}

async function quickCreateParty(): Promise<void> {
  if (!newPartyName.value) return;
  error.value = null;
  try {
    const created =
      props.kind === "sales"
        ? await store.createCustomer(newPartyName.value)
        : await store.createSupplier(newPartyName.value);
    partyId.value = created.id;
    newPartyName.value = "";
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

async function viewPdf(): Promise<void> {
  error.value = null;
  try {
    await openPdf(`${endpoint.value}/${doc.value!.id}/pdf`);
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

function goToPayment(): void {
  if (!doc.value) return;
  void router.push({
    name: "payment-entries",
    query: {
      type: props.kind === "sales" ? "Receive" : "Pay",
      party_id:
        props.kind === "sales"
          ? (doc.value as SalesInvoiceDetail).customer_id
          : (doc.value as PurchaseInvoiceDetail).supplier_id,
    },
  });
}

async function save(): Promise<void> {
  saving.value = true;
  error.value = null;
  try {
    const payload: Record<string, unknown> = {
      posting_date: postingDate.value,
      due_date: dueDate.value || null,
      items: items.value.filter((i) => i.item_name),
      taxes: taxes.value.filter((t) => t.account_head_id),
    };
    if (props.kind === "sales") payload.customer_id = partyId.value;
    else payload.supplier_id = partyId.value;
    const resp = await api.post<InvoiceDetail>(endpoint.value, payload);
    void router.push(`${endpoint.value}/${resp.data.id}`);
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
    doc.value = await store.docAction<InvoiceDetail>(endpoint.value, doc.value.id, name);
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

interface SourceItem {
  id: string;
  item_id: string | null;
  item_code: string | null;
  item_name: string | null;
  qty: string;
  rate: string;
  billed_qty?: string;
  billed_amt?: string;
  delivered_qty?: string;
  received_qty?: string;
  sales_order_item_id?: string | null;
  purchase_order_item_id?: string | null;
}

// "Create Invoice" from an order / delivery / receipt prefills the unbilled rows
async function prefillFromSource(): Promise<void> {
  const sources: Array<{
    param: string;
    endpoint: string;
    partyKey: "customer_id" | "supplier_id";
    link: (row: SourceItem) => Partial<InvoiceItemIn>;
    unbilled: (row: SourceItem) => number;
  }> = props.kind === "sales"
    ? [
        {
          param: "sales_order_id", endpoint: "/sales-orders", partyKey: "customer_id",
          link: (row) => ({ sales_order_item_id: row.id }),
          unbilled: (row) =>
            Number(row.rate) > 0
              ? Number(row.qty) - (Number(row.billed_amt) || 0) / Number(row.rate)
              : Number(row.qty),
        },
        {
          param: "delivery_note_id", endpoint: "/delivery-notes", partyKey: "customer_id",
          link: (row) => ({
            delivery_note_item_id: row.id,
            sales_order_item_id: row.sales_order_item_id ?? null,
          }),
          unbilled: (row) => Number(row.qty) - (Number(row.billed_qty) || 0),
        },
      ]
    : [
        {
          param: "purchase_order_id", endpoint: "/purchase-orders", partyKey: "supplier_id",
          link: (row) => ({ purchase_order_item_id: row.id }),
          unbilled: (row) =>
            Number(row.rate) > 0
              ? Number(row.qty) - (Number(row.billed_amt) || 0) / Number(row.rate)
              : Number(row.qty),
        },
        {
          param: "purchase_receipt_id", endpoint: "/purchase-receipts", partyKey: "supplier_id",
          link: (row) => ({
            purchase_receipt_item_id: row.id,
            purchase_order_item_id: row.purchase_order_item_id ?? null,
          }),
          unbilled: (row) => Number(row.qty) - (Number(row.billed_qty) || 0),
        },
      ];

  for (const source of sources) {
    const docId = route.query[source.param];
    if (typeof docId !== "string") continue;
    const sourceDoc = (
      await api.get<Record<string, unknown> & { items: SourceItem[] }>(`${source.endpoint}/${docId}`)
    ).data;
    partyId.value = String(sourceDoc[source.partyKey] ?? "");
    items.value = sourceDoc.items
      .map((row) => ({ row, pending: source.unbilled(row) }))
      .filter(({ pending }) => pending > 0.000001)
      .map(({ row, pending }) => ({
        item_name: row.item_name ?? row.item_code ?? "",
        item_code: row.item_code,
        qty: Math.round(pending * 1000) / 1000,
        rate: Number(row.rate),
        item_id: row.item_id,
        ...source.link(row),
      }));
    return;
  }
}

onMounted(async () => {
  await Promise.all([
    store.fetchAccounts(),
    props.kind === "sales" ? store.fetchCustomers() : store.fetchSuppliers(),
  ]);
  if (props.id) {
    doc.value = (await api.get<InvoiceDetail>(`${endpoint.value}/${props.id}`)).data;
  } else {
    await prefillFromSource();
  }
});
</script>

<template>
  <div class="max-w-5xl">
    <!-- existing invoice: detail + actions -->
    <div v-if="doc">
      <div class="mb-4 flex items-center justify-between">
        <div>
          <h1 class="text-xl font-semibold text-gray-900">{{ docPartyName || doc.name }}</h1>
          <p class="text-sm text-gray-500">{{ doc.name }}</p>
        </div>
        <div class="flex items-center gap-3">
          <StatusBadge :status="doc.status" />
          <button v-if="doc.docstatus === 0" class="btn-primary" @click="action('submit')">Submit</button>
          <button
            v-if="doc.docstatus === 1 && Number(doc.outstanding_amount) > 0"
            class="btn-primary"
            @click="goToPayment"
          >{{ kind === "sales" ? "Receive Payment" : "Pay" }}</button>
          <button v-if="doc.docstatus === 1" class="btn-secondary" @click="action('cancel')">Cancel</button>
          <button v-if="doc.docstatus === 1" class="btn-secondary" @click="viewPdf">PDF</button>
        </div>
      </div>
      <p v-if="error" class="mb-3 text-sm text-red-600">{{ error.detail }}</p>

      <div class="mb-4 grid grid-cols-2 gap-x-8 gap-y-3 rounded-lg border border-gray-200 bg-white p-5 shadow-sm md:grid-cols-4">
        <div>
          <div class="text-xs font-semibold uppercase tracking-wide text-gray-400">{{ partyLabel }}</div>
          <div class="mt-0.5 text-sm font-medium text-gray-900">{{ docPartyName || "—" }}</div>
        </div>
        <div>
          <div class="text-xs font-semibold uppercase tracking-wide text-gray-400">Posting Date</div>
          <div class="mt-0.5 text-sm text-gray-900">{{ formatDate(doc.posting_date) }}</div>
        </div>
        <div>
          <div class="text-xs font-semibold uppercase tracking-wide text-gray-400">Due Date</div>
          <div class="mt-0.5 text-sm text-gray-900">{{ formatDate(doc.due_date) }}</div>
        </div>
        <div>
          <div class="text-xs font-semibold uppercase tracking-wide text-gray-400">Currency</div>
          <div class="mt-0.5 text-sm text-gray-900">{{ doc.currency }}</div>
        </div>
        <div v-if="docBillNo">
          <div class="text-xs font-semibold uppercase tracking-wide text-gray-400">Supplier Invoice</div>
          <div class="mt-0.5 text-sm text-gray-900">{{ docBillNo }}</div>
        </div>
        <div v-if="doc.remarks" class="col-span-2 md:col-span-3">
          <div class="text-xs font-semibold uppercase tracking-wide text-gray-400">Remarks</div>
          <div class="mt-0.5 text-sm text-gray-700">{{ doc.remarks }}</div>
        </div>
      </div>

      <div class="rounded-lg border border-gray-200 bg-white shadow-sm">
        <table class="min-w-full text-sm">
          <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr><th class="px-4 py-2">#</th><th class="px-4 py-2">Item</th>
                <th class="px-4 py-2 text-right">Qty</th><th class="px-4 py-2 text-right">Rate</th>
                <th class="px-4 py-2 text-right">Amount</th></tr>
          </thead>
          <tbody>
            <tr v-for="item in doc.items" :key="item.idx" class="border-t border-gray-100">
              <td class="px-4 py-2">{{ item.idx }}</td>
              <td class="px-4 py-2 font-medium text-gray-900">{{ item.item_name }}</td>
              <td class="px-4 py-2 text-right">{{ formatQty(item.qty) }}</td>
              <td class="px-4 py-2 text-right">{{ money(item.rate) }}</td>
              <td class="px-4 py-2 text-right">{{ money(item.amount) }}</td>
            </tr>
          </tbody>
        </table>
        <div class="border-t border-gray-200 p-4">
          <dl class="ml-auto w-80 space-y-1 text-sm">
            <div class="flex justify-between"><dt class="text-gray-500">Net Total</dt><dd>{{ money(doc.net_total) }}</dd></div>
            <div v-for="tax in doc.taxes" :key="tax.idx" class="flex justify-between">
              <dt class="text-gray-500">{{ tax.description || tax.charge_type }} <template v-if="Number(tax.rate)">({{ Number(tax.rate) }}%)</template></dt>
              <dd>{{ money(tax.tax_amount) }}</dd>
            </div>
            <div v-if="Number(doc.discount_amount)" class="flex justify-between text-gray-500">
              <dt>Discount</dt><dd>-{{ money(doc.discount_amount) }}</dd>
            </div>
            <div class="flex justify-between border-t border-gray-200 pt-1 text-base font-semibold">
              <dt>Grand Total</dt><dd>{{ money(doc.rounded_total) }}</dd>
            </div>
            <!-- outstanding is tracked in company (base) currency -->
            <div class="flex justify-between" :class="Number(doc.outstanding_amount) > 0 ? 'font-medium text-red-700' : 'text-gray-500'">
              <dt>Outstanding</dt><dd>{{ formatCurrency(doc.outstanding_amount, companyCurrency) }}</dd>
            </div>
          </dl>
        </div>
      </div>
    </div>

    <!-- new invoice form -->
    <form v-else class="space-y-4" @submit.prevent="save">
      <h1 class="text-xl font-semibold text-gray-900">
        New {{ kind === "sales" ? "Sales" : "Purchase" }} Invoice
      </h1>
      <div class="grid grid-cols-3 gap-4 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <div>
          <label class="form-label">{{ partyLabel }}*</label>
          <select v-model="partyId" required class="form-input">
            <option value="" disabled>Select…</option>
            <option v-for="p in parties" :key="p.id" :value="p.id">
              {{ "customer_name" in p ? p.customer_name : p.supplier_name }}
            </option>
          </select>
          <div class="mt-1 flex gap-2">
            <input v-model="newPartyName" class="form-input" :placeholder="`Quick add ${partyLabel.toLowerCase()}…`" />
            <button type="button" class="btn-secondary" @click="quickCreateParty">Add</button>
          </div>
        </div>
        <div>
          <label class="form-label">Posting Date*</label>
          <input v-model="postingDate" type="date" required class="form-input" />
        </div>
        <div>
          <label class="form-label">Due Date</label>
          <input v-model="dueDate" type="date" class="form-input" />
        </div>
      </div>

      <div class="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <div class="mb-2 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-gray-900">Items</h2>
          <button type="button" class="btn-secondary" @click="addItem">Add Row</button>
        </div>
        <div v-for="(item, i) in items" :key="i" class="mb-2 grid grid-cols-12 gap-2">
          <input v-model="item.item_name" placeholder="Item name" class="form-input col-span-6" />
          <input v-model.number="item.qty" type="number" step="any" min="0" placeholder="Qty" class="form-input col-span-2" />
          <input v-model.number="item.rate" type="number" step="any" min="0" placeholder="Rate" class="form-input col-span-2" />
          <div class="col-span-2 flex items-center justify-end pr-2 text-sm text-gray-600">
            {{ formatNumber((item.qty || 0) * (item.rate || 0)) }}
          </div>
        </div>
        <p class="text-right text-sm font-medium text-gray-700">Net: {{ formatNumber(previewNet) }}</p>
      </div>

      <div class="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <div class="mb-2 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-gray-900">Taxes &amp; Charges</h2>
          <button type="button" class="btn-secondary" @click="addTax">Add Tax</button>
        </div>
        <div v-for="(tax, i) in taxes" :key="i" class="mb-2 grid grid-cols-12 gap-2">
          <select v-model="tax.charge_type" class="form-input col-span-3">
            <option>On Net Total</option>
            <option>On Previous Row Total</option>
            <option>On Previous Row Amount</option>
            <option>Actual</option>
            <option>On Item Quantity</option>
          </select>
          <input
            v-if="tax.charge_type === 'Actual'"
            v-model.number="tax.tax_amount"
            type="number"
            step="any"
            min="0"
            placeholder="Amount"
            class="form-input col-span-2"
          />
          <input
            v-else
            v-model.number="tax.rate"
            type="number"
            step="any"
            placeholder="Rate %"
            class="form-input col-span-2"
          />
          <select v-model="tax.account_head_id" class="form-input col-span-5">
            <option value="" disabled>Tax account…</option>
            <option v-for="opt in store.accountOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
          <input
            v-if="tax.charge_type.startsWith('On Previous')"
            v-model.number="tax.row_id"
            type="number"
            min="1"
            placeholder="Row #"
            class="form-input col-span-2"
          />
        </div>
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
