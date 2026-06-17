<script setup lang="ts">
// Shared "Currency" section. v-model holds the document currency + exchange
// rate. The exchange-rate input only appears for a non-company currency.
// (Price-list selection is intentionally deferred — the backend resolves item
// rates from the default selling price list server-side.)

export interface CurrencyModel {
  currency: string;
  conversion_rate: number;
}

const props = defineProps<{ modelValue: CurrencyModel; companyCurrency: string }>();
const emit = defineEmits<{ "update:modelValue": [value: CurrencyModel] }>();

function setCurrency(e: Event): void {
  const currency = (e.target as HTMLInputElement).value.toUpperCase().slice(0, 3);
  // Reset the rate to 1 when switching back to the company currency.
  const conversion_rate =
    currency === props.companyCurrency.toUpperCase() ? 1 : props.modelValue.conversion_rate;
  emit("update:modelValue", { currency, conversion_rate });
}
function setRate(e: Event): void {
  const v = (e.target as HTMLInputElement).value;
  emit("update:modelValue", { ...props.modelValue, conversion_rate: v === "" ? 1 : Number(v) });
}
</script>

<template>
  <div>
    <h2 class="mb-2 text-sm font-semibold text-gray-900">Currency</h2>
    <div class="grid grid-cols-1 gap-x-8 gap-y-4 md:grid-cols-3">
      <div>
        <label class="form-label">Currency</label>
        <input
          type="text"
          class="form-input uppercase"
          maxlength="3"
          pattern="[A-Za-z]{3}"
          title="3-letter currency code (e.g. INR), or leave blank for the company default"
          :value="modelValue.currency"
          :placeholder="companyCurrency"
          @input="setCurrency"
        />
      </div>
      <div v-if="modelValue.currency && modelValue.currency !== companyCurrency">
        <label class="form-label">Exchange Rate</label>
        <input
          type="number"
          step="any"
          min="0"
          class="form-input"
          :value="modelValue.conversion_rate"
          @input="setRate"
        />
        <p class="mt-1 text-xs text-gray-400">1 {{ modelValue.currency }} = ? {{ companyCurrency }}</p>
      </div>
    </div>
  </div>
</template>
