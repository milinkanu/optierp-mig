<script setup lang="ts">
// ERPNext-style editable items grid for transaction forms (Quotation, Sales
// Order, Sales Invoice, …). Renders one column per configured field plus a
// computed Amount column, a per-row remove control, "Add row"/"Add multiple",
// and a Total Quantity / Total footer. Two-way bound via v-model; selecting an
// item emits `item-change` so the parent can resolve the rate.

import { computed, ref, watch } from "vue";
import { formatCurrency } from "@/utils/format";
import { rowKey } from "@/utils/rowKey";
import DateField from "@/components/shared/DateField.vue";

export interface GridColumn {
  key: string;
  label: string;
  type: "item" | "select" | "number" | "date" | "text";
  align?: "left" | "right";
  required?: boolean;
  options?: { value: string; label: string }[]; // for type "select"
}

type Row = Record<string, unknown>;

const props = defineProps<{
  modelValue: Row[];
  columns: GridColumn[];
  itemOptions: { value: string; label: string }[];
  currency: string;
  newRow: () => Row;
  qtyKey?: string;
  rateKey?: string;
}>();

const emit = defineEmits<{
  "update:modelValue": [rows: Row[]];
  "item-change": [index: number];
}>();

// Ensure every row carries a stable key so deletes/reorders don't strand child
// state on the wrong row. Backfills rows added without one (import, prefill).
watch(
  () => props.modelValue,
  (rows) => {
    if (rows.some((r) => r._rowKey == null)) {
      emit(
        "update:modelValue",
        rows.map((r) => (r._rowKey == null ? { ...r, _rowKey: rowKey() } : r)),
      );
    }
  },
  { immediate: true },
);

const qtyKey = computed(() => props.qtyKey ?? "qty");
const rateKey = computed(() => props.rateKey ?? "rate");
const itemKey = computed(() => props.columns.find((c) => c.type === "item")?.key ?? null);

function amountOf(row: Row): number {
  return (Number(row[qtyKey.value]) || 0) * (Number(row[rateKey.value]) || 0);
}
const totalQty = computed(() =>
  props.modelValue.reduce((sum, r) => sum + (Number(r[qtyKey.value]) || 0), 0),
);
const totalAmount = computed(() =>
  props.modelValue.reduce((sum, r) => sum + amountOf(r), 0),
);

function patch(index: number, key: string, value: unknown): void {
  emit(
    "update:modelValue",
    props.modelValue.map((r, i) => (i === index ? { ...r, [key]: value } : r)),
  );
}

function onCell(index: number, col: GridColumn, event: Event): void {
  const target = event.target as HTMLInputElement | HTMLSelectElement;
  let value: unknown = target.value;
  if (col.type === "number") value = target.value === "" ? null : Number(target.value);
  // an empty optional link (e.g. Warehouse) must be null, not "" (UUID|None on the backend)
  else if (col.type === "select") value = target.value === "" ? null : target.value;
  patch(index, col.key, value);
  if (col.type === "item") emit("item-change", index);
}

function addRow(): void {
  emit("update:modelValue", [...props.modelValue, props.newRow()]);
}
function removeRow(index: number): void {
  emit(
    "update:modelValue",
    props.modelValue.filter((_, i) => i !== index),
  );
}

// --- Add multiple ----------------------------------------------------------
const showMulti = ref(false);
const multiFilter = ref("");
const multiSelected = ref<Set<string>>(new Set());

const filteredOptions = computed(() => {
  const q = multiFilter.value.trim().toLowerCase();
  if (!q) return props.itemOptions;
  return props.itemOptions.filter((o) => o.label.toLowerCase().includes(q));
});

function openMulti(): void {
  multiSelected.value = new Set();
  multiFilter.value = "";
  showMulti.value = true;
}
function toggleMulti(value: string): void {
  const next = new Set(multiSelected.value);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  multiSelected.value = next;
}
function confirmMulti(): void {
  const key = itemKey.value;
  if (!key || multiSelected.value.size === 0) {
    showMulti.value = false;
    return;
  }
  const base = props.modelValue.length;
  const ids = [...multiSelected.value];
  const additions = ids.map((id) => ({ ...props.newRow(), [key]: id }));
  emit("update:modelValue", [...props.modelValue, ...additions]);
  ids.forEach((_, i) => emit("item-change", base + i));
  showMulti.value = false;
}
</script>

<template>
  <div>
    <div class="overflow-x-auto rounded-lg border border-gray-200">
      <table class="min-w-full divide-y divide-gray-200 text-sm">
        <thead class="bg-gray-50">
          <tr>
            <th class="w-12 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">No.</th>
            <th
              v-for="col in columns"
              :key="col.key"
              class="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-gray-500"
              :class="col.align === 'right' ? 'text-right' : 'text-left'"
            >
              {{ col.label }}<span v-if="col.required" class="text-red-500">&nbsp;*</span>
            </th>
            <th class="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-gray-500">Amount</th>
            <th class="w-10 px-3 py-2"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          <tr v-if="modelValue.length === 0">
            <td :colspan="columns.length + 3" class="px-3 py-6 text-center text-gray-400">No rows</td>
          </tr>
          <tr v-for="(row, i) in modelValue" :key="(row._rowKey as string) ?? i" class="hover:bg-gray-50/60">
            <td class="px-3 py-1.5 text-gray-500">{{ i + 1 }}</td>
            <td v-for="col in columns" :key="col.key" class="px-3 py-1.5">
              <select
                v-if="col.type === 'item'"
                class="form-input py-1.5"
                :value="(row[col.key] as string) ?? ''"
                @change="onCell(i, col, $event)"
              >
                <option value="" disabled>Select item…</option>
                <option v-for="o in itemOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
              <DateField
                v-else-if="col.type === 'date'"
                :model-value="(row[col.key] as string) ?? ''"
                @update:model-value="patch(i, col.key, $event)"
              />
              <select
                v-else-if="col.type === 'select'"
                class="form-input py-1.5"
                :value="(row[col.key] as string) ?? ''"
                @change="onCell(i, col, $event)"
              >
                <option value="">—</option>
                <option v-for="o in col.options ?? []" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
              <input
                v-else
                :type="col.type === 'number' ? 'number' : 'text'"
                :step="col.type === 'number' ? 'any' : undefined"
                :min="col.type === 'number' ? '0' : undefined"
                class="form-input py-1.5"
                :class="col.align === 'right' ? 'text-right' : ''"
                :value="(row[col.key] as string | number | null) ?? ''"
                @input="onCell(i, col, $event)"
              />
            </td>
            <td class="px-3 py-1.5 text-right tabular-nums text-gray-700">
              {{ formatCurrency(amountOf(row), currency) }}
            </td>
            <td class="px-3 py-1.5 text-right">
              <button
                type="button"
                class="text-gray-400 hover:text-red-600"
                title="Remove row"
                @click="removeRow(i)"
              >
                ✕
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="mt-2 flex items-center gap-2">
      <button type="button" class="btn-secondary" @click="addRow">Add row</button>
      <button type="button" class="btn-secondary" @click="openMulti">Add multiple</button>
    </div>

    <!-- Totals -->
    <div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div>
        <div class="form-label">Total Quantity</div>
        <div class="form-input bg-gray-50 tabular-nums text-gray-700">{{ totalQty }}</div>
      </div>
      <div>
        <div class="form-label">Total ({{ currency }})</div>
        <div class="form-input bg-gray-50 tabular-nums text-gray-700">{{ formatCurrency(totalAmount, currency) }}</div>
      </div>
    </div>

    <!-- Add multiple dialog -->
    <div
      v-if="showMulti"
      class="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4"
      @click.self="showMulti = false"
    >
      <div class="w-full max-w-lg rounded-lg bg-white p-5 shadow-xl">
        <h3 class="mb-3 text-sm font-semibold text-gray-900">Add multiple items</h3>
        <input v-model="multiFilter" class="form-input mb-3" placeholder="Search items…" />
        <div class="max-h-72 overflow-y-auto rounded-md border border-gray-200">
          <label
            v-for="o in filteredOptions"
            :key="o.value"
            class="flex cursor-pointer items-center gap-2 border-b border-gray-100 px-3 py-2 text-sm last:border-b-0 hover:bg-gray-50"
          >
            <input
              type="checkbox"
              class="h-4 w-4 rounded border-gray-300 text-primary"
              :checked="multiSelected.has(o.value)"
              @change="toggleMulti(o.value)"
            />
            <span class="text-gray-700">{{ o.label }}</span>
          </label>
          <p v-if="filteredOptions.length === 0" class="px-3 py-4 text-center text-sm text-gray-400">No items</p>
        </div>
        <div class="mt-4 flex items-center justify-between">
          <span class="text-xs text-gray-500">{{ multiSelected.size }} selected</span>
          <div class="flex gap-2">
            <button type="button" class="btn-secondary" @click="showMulti = false">Cancel</button>
            <button type="button" class="btn-primary" :disabled="multiSelected.size === 0" @click="confirmMulti">
              Add {{ multiSelected.size || "" }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
