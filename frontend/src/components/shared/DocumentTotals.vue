<script setup lang="ts">
// Shared "Totals" block — a live preview of net / taxes / discount / grand /
// rounded total + amount in words, mirroring ERPNext. The backend recomputes
// authoritatively on save.

import { computed } from "vue";
import { formatCurrency } from "@/utils/format";
import {
  amountInWords,
  computeTotals,
  type TotalsDiscount,
  type TotalsItem,
  type TotalsTax,
} from "@/utils/totals";

const props = defineProps<{
  items: TotalsItem[];
  taxes: TotalsTax[];
  discount: TotalsDiscount;
  currency: string;
}>();

const t = computed(() => computeTotals(props.items, props.taxes, props.discount));
const inWords = computed(() => amountInWords(t.value.roundedTotal, props.currency));
const money = (v: number): string => formatCurrency(v, props.currency);
</script>

<template>
  <div>
    <h2 class="mb-2 text-sm font-semibold text-gray-900">Totals</h2>
    <dl class="ml-auto max-w-md space-y-1 text-sm">
      <div class="flex justify-between">
        <dt class="text-gray-500">Net Total</dt>
        <dd class="tabular-nums">{{ money(t.netTotal) }}</dd>
      </div>
      <div v-if="t.totalTaxes !== 0" class="flex justify-between">
        <dt class="text-gray-500">Total Taxes and Charges</dt>
        <dd class="tabular-nums">{{ money(t.totalTaxes) }}</dd>
      </div>
      <div v-if="t.discountAmount !== 0" class="flex justify-between text-gray-500">
        <dt>Discount</dt>
        <dd class="tabular-nums">-{{ money(t.discountAmount) }}</dd>
      </div>
      <div class="flex justify-between border-t border-gray-200 pt-1 font-medium text-gray-900">
        <dt>Grand Total</dt>
        <dd class="tabular-nums">{{ money(t.grandTotal) }}</dd>
      </div>
      <div v-if="t.roundingAdjustment !== 0" class="flex justify-between text-gray-500">
        <dt>Rounding Adjustment</dt>
        <dd class="tabular-nums">{{ money(t.roundingAdjustment) }}</dd>
      </div>
      <div class="flex justify-between border-t border-gray-200 pt-1 text-base font-semibold text-gray-900">
        <dt>Rounded Total</dt>
        <dd class="tabular-nums">{{ money(t.roundedTotal) }}</dd>
      </div>
      <div class="pt-1 text-right text-xs italic text-gray-400">{{ inWords }}</div>
    </dl>
  </div>
</template>
