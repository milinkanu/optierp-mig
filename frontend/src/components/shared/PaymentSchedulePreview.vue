<script setup lang="ts">
// Read-only payment due-date breakdown for a chosen Payment Terms Template.
// Fetches the template's installments once, then derives rows from the document
// total + posting date (see utils/paymentSchedule). Renders nothing when no
// template is selected.

import { computed, ref, watch } from "vue";
import { api } from "@/api/client";
import { formatCurrency, formatDate } from "@/utils/format";
import {
  buildPaymentSchedule,
  totalPortion,
  type PaymentInstallment,
} from "@/utils/paymentSchedule";

const props = defineProps<{
  templateId: string | null | undefined;
  total: number;
  postingDate: string;
  currency: string;
}>();

const installments = ref<PaymentInstallment[]>([]);
const templateName = ref<string>("");
const loading = ref(false);

watch(
  () => props.templateId,
  async (id) => {
    installments.value = [];
    templateName.value = "";
    if (!id) return;
    loading.value = true;
    try {
      const resp = await api.get<{ terms?: PaymentInstallment[]; template_name?: string }>(
        `/registry/payment-terms-template/${id}`,
      );
      installments.value = resp.data.terms ?? [];
      templateName.value = resp.data.template_name ?? "";
    } catch {
      installments.value = [];
    } finally {
      loading.value = false;
    }
  },
  { immediate: true },
);

const rows = computed(() =>
  buildPaymentSchedule(installments.value, props.total, props.postingDate),
);
const portionSum = computed(() => totalPortion(installments.value));
</script>

<template>
  <div v-if="templateId && rows.length" class="mt-3">
    <div class="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
      Payment Terms<span v-if="templateName" class="ml-1 normal-case text-gray-600">· {{ templateName }}</span>
    </div>
    <table class="min-w-full max-w-lg text-sm">
      <thead class="text-left text-xs uppercase text-gray-500">
        <tr>
          <th class="py-1 pr-4">Installment</th>
          <th class="py-1 pr-4 text-right">%</th>
          <th class="py-1 pr-4">Due Date</th>
          <th class="py-1 text-right">Amount</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(r, i) in rows" :key="i" class="border-t border-gray-100">
          <td class="py-1 pr-4 text-gray-700">{{ r.label }}</td>
          <td class="py-1 pr-4 text-right tabular-nums text-gray-500">{{ r.portion }}%</td>
          <td class="py-1 pr-4 text-gray-700">{{ formatDate(r.dueDate) }}</td>
          <td class="py-1 text-right tabular-nums text-gray-900">{{ formatCurrency(r.amount, currency) }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="Math.abs(portionSum - 100) > 0.001" class="mt-1 text-xs text-amber-600">
      ⚠ Installments add up to {{ portionSum }}%, not 100% — check the template.
    </p>
  </div>
</template>
