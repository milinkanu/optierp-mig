<script setup lang="ts">
// Journal Entry list + creation in one view (rows editor with live balance).

import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import DataTable, { type Column } from "@/components/shared/DataTable.vue";
import PaginationFooter from "@/components/shared/PaginationFooter.vue";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import { useList } from "@/composables/useList";
import { useAccountsStore } from "@/stores/accounts";
import { useCompanyCurrency } from "@/composables/useCompanyCurrency";
import { api } from "@/api/client";
import { formatCurrency, formatDate, formatNumber } from "@/utils/format";
import type { ErrorEnvelope } from "@/types/core";
import type { JournalEntryListItem, JournalEntryRowIn } from "@/types/accounts";

const router = useRouter();
const store = useAccountsStore();
const openDetail = (row: JournalEntryListItem): void => void router.push(`/journal-entries/${row.id}`);
const companyCurrency = useCompanyCurrency();
const { items, total, page, pageSize, loading, fetchList, goToPage } = useList<JournalEntryListItem>("/journal-entries");

const showForm = ref(false);
const postingDate = ref(new Date().toISOString().slice(0, 10));
const remarks = ref("");
const rows = ref<JournalEntryRowIn[]>([
  { account_id: "", debit: 0, credit: 0 },
  { account_id: "", debit: 0, credit: 0 },
]);
const error = ref<ErrorEnvelope | null>(null);
const saving = ref(false);

const totalDebit = computed(() => rows.value.reduce((s, r) => s + (Number(r.debit) || 0), 0));
const totalCredit = computed(() => rows.value.reduce((s, r) => s + (Number(r.credit) || 0), 0));
const balanced = computed(
  () => Math.abs(totalDebit.value - totalCredit.value) < 0.005 && totalDebit.value > 0,
);

const columns: Column[] = [
  { key: "name", label: "Entry" },
  { key: "posting_date", label: "Date" },
  { key: "voucher_type", label: "Type" },
  { key: "total_debit", label: "Amount", class: "text-right" },
  { key: "docstatus", label: "Status" },
];

async function save(): Promise<void> {
  saving.value = true;
  error.value = null;
  try {
    const resp = await api.post("/journal-entries", {
      posting_date: postingDate.value,
      remarks: remarks.value || null,
      accounts: rows.value.filter((r) => r.account_id),
    });
    await api.post(`/journal-entries/${(resp.data as { id: string }).id}/submit`);
    showForm.value = false;
    rows.value = [
      { account_id: "", debit: 0, credit: 0 },
      { account_id: "", debit: 0, credit: 0 },
    ];
    await fetchList();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    saving.value = false;
  }
}

async function cancelEntry(row: JournalEntryListItem): Promise<void> {
  if (row.docstatus !== 1) return;
  try {
    await api.post(`/journal-entries/${row.id}/cancel`);
    await fetchList();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

onMounted(async () => {
  await Promise.all([fetchList(), store.fetchAccounts()]);
});
</script>

<template>
  <div>
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">Journal Entries</h1>
        <p class="text-sm text-gray-500">{{ total }} total</p>
      </div>
      <button class="btn-primary" @click="showForm = !showForm">
        {{ showForm ? "Close" : "New Journal Entry" }}
      </button>
    </div>

    <form v-if="showForm" class="mb-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm" @submit.prevent="save">
      <div class="mb-3 grid grid-cols-3 gap-4">
        <div>
          <label class="form-label">Posting Date*</label>
          <input v-model="postingDate" type="date" required class="form-input" />
        </div>
        <div class="col-span-2">
          <label class="form-label">Remarks</label>
          <input v-model="remarks" class="form-input" placeholder="e.g. Office rent for June" />
        </div>
      </div>
      <div v-for="(row, i) in rows" :key="i" class="mb-2 grid grid-cols-12 gap-2">
        <select v-model="row.account_id" class="form-input col-span-6">
          <option value="" disabled>Account…</option>
          <option v-for="opt in store.accountOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <input v-model.number="row.debit" type="number" min="0" step="any" placeholder="Debit" class="form-input col-span-3" />
        <input v-model.number="row.credit" type="number" min="0" step="any" placeholder="Credit" class="form-input col-span-3" />
      </div>
      <div class="mt-2 flex items-center justify-between">
        <button type="button" class="btn-secondary" @click="rows.push({ account_id: '', debit: 0, credit: 0 })">
          Add Row
        </button>
        <div class="text-sm" :class="balanced ? 'text-green-600' : 'text-red-600'">
          Dr {{ formatNumber(totalDebit) }} / Cr {{ formatNumber(totalCredit) }}
          {{ balanced ? "✓ balanced" : "— must balance" }}
        </div>
      </div>
      <p v-if="error" class="mt-2 text-sm text-red-600">{{ error.detail }}</p>
      <div class="mt-4 flex justify-end">
        <button type="submit" class="btn-primary" :disabled="!balanced || saving">
          {{ saving ? "Posting…" : "Save & Submit" }}
        </button>
      </div>
    </form>

    <DataTable :columns="columns" :rows="items" :loading="loading" @row-click="openDetail">
      <template #cell-name="{ row }">
        <span class="font-medium text-primary">{{ row.name }}</span>
      </template>
      <template #cell-posting_date="{ value }">
        {{ formatDate(String(value)) }}
      </template>
      <template #cell-total_debit="{ value }">
        {{ formatCurrency(String(value), companyCurrency) }}
      </template>
      <template #cell-docstatus="{ value, row }">
        <div class="flex items-center gap-2">
          <StatusBadge :status="Number(value)" />
          <button
            v-if="value === 1"
            class="text-xs text-red-600 hover:underline"
            @click.stop="cancelEntry(row)"
          >cancel</button>
        </div>
      </template>
    </DataTable>
    <PaginationFooter :page="page" :page-size="pageSize" :total="total" @go-to="goToPage" />
  </div>
</template>
