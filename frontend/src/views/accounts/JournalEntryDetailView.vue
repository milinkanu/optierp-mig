<script setup lang="ts">
// Read-only Journal Entry detail. Reachable from the Journal Entry list and the
// Bank Reconciliation tool — shows the balanced debit/credit lines + clearance.

import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client";
import { useAccountsStore } from "@/stores/accounts";
import { useCompanyCurrency } from "@/composables/useCompanyCurrency";
import { formatCurrency, formatDate } from "@/utils/format";
import type { ErrorEnvelope } from "@/types/core";
import type { JournalEntryDetail } from "@/types/accounts";

const props = defineProps<{ id: string }>();
const router = useRouter();
const store = useAccountsStore();
const companyCurrency = useCompanyCurrency();
const money = (v: string | number | null | undefined): string => formatCurrency(v, companyCurrency.value);

const doc = ref<JournalEntryDetail | null>(null);
const error = ref<ErrorEnvelope | null>(null);

const accountMap = computed<Record<string, string>>(() => {
  const m: Record<string, string> = {};
  for (const a of store.accountOptions) m[a.value] = a.label;
  return m;
});
const accountName = (id: string): string => accountMap.value[id] ?? "—";

onMounted(async () => {
  void store.fetchAccounts();
  try {
    doc.value = (await api.get<JournalEntryDetail>(`/journal-entries/${props.id}`)).data;
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
});
</script>

<template>
  <div class="mx-auto max-w-3xl">
    <button class="mb-3 text-sm text-gray-500 hover:text-gray-800" @click="router.back()">← Back</button>
    <p v-if="error" class="mb-3 text-sm text-red-600">{{ error.detail }}</p>

    <div v-if="doc">
      <div class="mb-4">
        <h1 class="text-xl font-semibold text-gray-900">{{ doc.name }}</h1>
        <p class="text-sm text-gray-500">
          {{ doc.voucher_type }} · {{ formatDate(doc.posting_date) }}
          <template v-if="doc.clearance_date"> · cleared {{ formatDate(doc.clearance_date) }}</template>
        </p>
      </div>

      <p v-if="doc.remarks" class="mb-4 rounded-lg border border-gray-200 bg-white p-3 text-sm text-gray-600 shadow-sm">
        {{ doc.remarks }}
      </p>

      <div class="rounded-lg border border-gray-200 bg-white shadow-sm">
        <table class="min-w-full text-sm">
          <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th class="px-4 py-2">Account</th>
              <th class="px-4 py-2 text-right">Debit</th>
              <th class="px-4 py-2 text-right">Credit</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in doc.accounts" :key="r.idx" class="border-t border-gray-100">
              <td class="px-4 py-2">
                {{ accountName(r.account_id) }}
                <span v-if="r.user_remark" class="text-xs text-gray-400"> — {{ r.user_remark }}</span>
              </td>
              <td class="px-4 py-2 text-right tabular-nums">{{ Number(r.debit) ? money(r.debit) : "" }}</td>
              <td class="px-4 py-2 text-right tabular-nums">{{ Number(r.credit) ? money(r.credit) : "" }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="border-t border-gray-200 bg-gray-50 font-semibold">
              <td class="px-4 py-2 text-right">Total</td>
              <td class="px-4 py-2 text-right tabular-nums">{{ money(doc.total_debit) }}</td>
              <td class="px-4 py-2 text-right tabular-nums">{{ money(doc.total_credit) }}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  </div>
</template>
