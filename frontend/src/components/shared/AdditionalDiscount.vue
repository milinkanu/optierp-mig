<script setup lang="ts">
// Shared "Additional Discount" section. v-model is a discount config object;
// either a percentage or a fixed amount, applied on Net or Grand Total.

export interface DiscountModel {
  apply_discount_on: string; // "Grand Total" | "Net Total"
  additional_discount_percentage: number;
  discount_amount: number;
}

const props = defineProps<{ modelValue: DiscountModel }>();
const emit = defineEmits<{ "update:modelValue": [value: DiscountModel] }>();

function patch(key: keyof DiscountModel, value: unknown): void {
  emit("update:modelValue", { ...props.modelValue, [key]: value });
}
function onNum(key: keyof DiscountModel, e: Event): void {
  const v = (e.target as HTMLInputElement).value;
  patch(key, v === "" ? 0 : Number(v));
}
</script>

<template>
  <div>
    <h2 class="mb-2 text-sm font-semibold text-gray-900">Additional Discount</h2>
    <div class="grid grid-cols-1 gap-x-8 gap-y-4 md:grid-cols-3">
      <div>
        <label class="form-label">Apply Discount On</label>
        <select
          class="form-input"
          :value="modelValue.apply_discount_on"
          @change="patch('apply_discount_on', ($event.target as HTMLSelectElement).value)"
        >
          <option>Grand Total</option>
          <option>Net Total</option>
        </select>
      </div>
      <div>
        <label class="form-label">Discount (%)</label>
        <input
          type="number"
          step="any"
          min="0"
          class="form-input"
          :value="modelValue.additional_discount_percentage || ''"
          placeholder="0"
          @input="onNum('additional_discount_percentage', $event)"
        />
      </div>
      <div>
        <label class="form-label">Discount Amount</label>
        <input
          type="number"
          step="any"
          min="0"
          class="form-input"
          :value="modelValue.discount_amount || ''"
          placeholder="0"
          @input="onNum('discount_amount', $event)"
        />
      </div>
    </div>
    <p class="mt-1 text-xs text-gray-400">A fixed Discount Amount takes precedence over the percentage.</p>
  </div>
</template>
