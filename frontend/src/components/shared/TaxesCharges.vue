<script setup lang="ts">
// Shared "Taxes & Charges" editor for transaction forms. v-model is a list of
// tax rows (charge type, rate or fixed amount, tax account, optional row ref).
// The backend recomputes amounts on save; this is the entry UI.

import type { TaxRowIn } from "@/types/accounts";

const props = defineProps<{
  modelValue: TaxRowIn[];
  accountOptions: { value: string; label: string }[];
}>();
const emit = defineEmits<{ "update:modelValue": [rows: TaxRowIn[]] }>();

const CHARGE_TYPES = [
  "On Net Total",
  "On Previous Row Total",
  "On Previous Row Amount",
  "Actual",
  "On Item Quantity",
];

function addTax(): void {
  emit("update:modelValue", [
    ...props.modelValue,
    { charge_type: "On Net Total", rate: 0, account_head_id: "" },
  ]);
}
function removeTax(i: number): void {
  emit("update:modelValue", props.modelValue.filter((_, idx) => idx !== i));
}
function patch(i: number, key: keyof TaxRowIn, value: unknown): void {
  emit(
    "update:modelValue",
    props.modelValue.map((r, idx) => (idx === i ? { ...r, [key]: value } : r)),
  );
}
function onNum(i: number, key: keyof TaxRowIn, e: Event): void {
  const v = (e.target as HTMLInputElement).value;
  // rate / tax_amount are non-nullable Decimals on the backend (clear -> 0);
  // row_id is an optional reference (clear -> null).
  if (key === "row_id") patch(i, key, v === "" ? null : Number(v));
  else patch(i, key, v === "" ? 0 : Number(v));
}
</script>

<template>
  <div>
    <div class="mb-2 flex items-center justify-between">
      <h2 class="text-sm font-semibold text-gray-900">Taxes &amp; Charges</h2>
      <button type="button" class="btn-secondary" @click="addTax">Add Tax</button>
    </div>
    <div
      v-if="modelValue.length === 0"
      class="rounded-lg border border-dashed border-gray-200 px-3 py-4 text-center text-sm text-gray-400"
    >
      No taxes
    </div>
    <div v-for="(tax, i) in modelValue" :key="i" class="mb-2 grid grid-cols-12 gap-2">
      <select
        class="form-input col-span-3"
        :value="tax.charge_type"
        @change="patch(i, 'charge_type', ($event.target as HTMLSelectElement).value)"
      >
        <option v-for="c in CHARGE_TYPES" :key="c" :value="c">{{ c }}</option>
      </select>
      <input
        v-if="tax.charge_type === 'Actual'"
        type="number"
        step="any"
        min="0"
        placeholder="Amount"
        class="form-input col-span-2"
        :value="tax.tax_amount ?? ''"
        @input="onNum(i, 'tax_amount', $event)"
      />
      <input
        v-else
        type="number"
        step="any"
        placeholder="Rate %"
        class="form-input col-span-2"
        :value="tax.rate ?? ''"
        @input="onNum(i, 'rate', $event)"
      />
      <select
        class="form-input col-span-5"
        :value="tax.account_head_id"
        @change="patch(i, 'account_head_id', ($event.target as HTMLSelectElement).value)"
      >
        <option value="" disabled>Tax account…</option>
        <option v-for="opt in accountOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
      </select>
      <input
        v-if="tax.charge_type.startsWith('On Previous')"
        type="number"
        min="1"
        placeholder="Row #"
        class="form-input col-span-1"
        :value="tax.row_id ?? ''"
        @input="onNum(i, 'row_id', $event)"
      />
      <button
        type="button"
        class="col-span-1 text-gray-400 hover:text-red-600"
        title="Remove tax"
        @click="removeTax(i)"
      >
        ✕
      </button>
    </div>
  </div>
</template>
