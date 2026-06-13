<script setup lang="ts">
// Budgets: list + creation; submitted budgets cap expense GL postings.

import { computed, onMounted, ref } from "vue";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import { useAccountsStore } from "@/stores/accounts";
import { formatCurrency } from "@/utils/format";
import { api } from "@/api/client";
import type { AccountNode, ErrorEnvelope, ListResponse } from "@/types/core";
import type { Budget, FiscalYearInfo } from "@/types/accounts";

const store = useAccountsStore();

const budgets = ref<Budget[]>([]);
const fiscalYears = ref<FiscalYearInfo[]>([]);
const error = ref<ErrorEnvelope | null>(null);
const saving = ref(false);
const showForm = ref(false);

const fiscalYearId = ref("");
const action = ref<"Stop" | "Warn" | "Ignore">("Warn");
const rows = ref<Array<{ account_id: string; budget_amount: number }>>([
  { account_id: "", budget_amount: 0 },
]);

const budgetableAccounts = computed(() =>
  store.leafAccounts.filter(
    (a: AccountNode) => a.root_type === "Expense" || a.root_type === "Income",
  ),
);
const fiscalYearLabel = computed(() => {
  const byId = new Map(fiscalYears.value.map((fy) => [fy.id, fy.year]));
  return (id: string): string => byId.get(id) ?? id;
});
const accountLabel = computed(() => {
  const byId = new Map(store.accounts.map((a: AccountNode) => [a.id, a.account_name]));
  return (id: string): string => byId.get(id) ?? id;
});

const docstatusLabel = (d: number): string => (d === 0 ? "Draft" : d === 1 ? "Submitted" : "Cancelled");

async function fetchBudgets(): Promise<void> {
  const resp = await api.get<ListResponse<Budget>>("/budgets", { params: { page_size: 100 } });
  budgets.value = resp.data.items;
}

function addRow(): void {
  rows.value.push({ account_id: "", budget_amount: 0 });
}

async function save(): Promise<void> {
  saving.value = true;
  error.value = null;
  try {
    await api.post("/budgets", {
      fiscal_year_id: fiscalYearId.value,
      action_if_annual_budget_exceeded: action.value,
      accounts: rows.value.filter((r) => r.account_id && Number(r.budget_amount) > 0),
    });
    showForm.value = false;
    rows.value = [{ account_id: "", budget_amount: 0 }];
    await fetchBudgets();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    saving.value = false;
  }
}

async function docAction(id: string, name: "submit" | "cancel"): Promise<void> {
  error.value = null;
  try {
    await api.post(`/budgets/${id}/${name}`);
    await fetchBudgets();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

onMounted(async () => {
  await Promise.all([store.fetchAccounts(), fetchBudgets()]);
  try {
    const resp = await api.get<ListResponse<FiscalYearInfo>>("/fiscal-years");
    fiscalYears.value = resp.data.items;
  } catch {
    fiscalYears.value = [];
  }
});
</script>

<template>
  <div class="max-w-5xl">
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">Budgets</h1>
        <p class="text-sm text-gray-500">
          Submitted budgets stop or warn on expense postings beyond the cap.
        </p>
      </div>
      <button class="btn-primary" @click="showForm = !showForm">
        {{ showForm ? "Close" : "New Budget" }}
      </button>
    </div>

    <p v-if="error" class="mb-3 text-sm text-red-600">{{ error.detail }}</p>

    <form v-if="showForm" class="mb-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm" @submit.prevent="save">
      <div class="grid grid-cols-3 gap-4">
        <div>
          <label class="form-label">Fiscal Year*</label>
          <select v-model="fiscalYearId" required class="form-input">
            <option value="" disabled>Select…</option>
            <option v-for="fy in fiscalYears" :key="fy.id" :value="fy.id">{{ fy.year }}</option>
          </select>
        </div>
        <div>
          <label class="form-label">If exceeded</label>
          <select v-model="action" class="form-input">
            <option>Stop</option>
            <option>Warn</option>
            <option>Ignore</option>
          </select>
        </div>
      </div>

      <div class="mt-4">
        <div class="mb-2 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-gray-900">Budget Accounts</h2>
          <button type="button" class="btn-secondary" @click="addRow">Add Row</button>
        </div>
        <div v-for="(row, i) in rows" :key="i" class="mb-2 grid grid-cols-12 gap-2">
          <select v-model="row.account_id" class="form-input col-span-8">
            <option value="" disabled>Income/Expense account…</option>
            <option v-for="a in budgetableAccounts" :key="a.id" :value="a.id">
              {{ a.account_name }} ({{ a.root_type }})
            </option>
          </select>
          <input
            v-model.number="row.budget_amount"
            type="number"
            min="0"
            step="any"
            placeholder="Annual amount"
            class="form-input col-span-4"
          />
        </div>
      </div>

      <div class="mt-4 flex justify-end">
        <button type="submit" class="btn-primary" :disabled="saving || !fiscalYearId">
          {{ saving ? "Saving…" : "Save Draft" }}
        </button>
      </div>
    </form>

    <div class="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      <table class="min-w-full text-sm">
        <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
          <tr>
            <th class="px-4 py-2">Fiscal Year</th>
            <th class="px-4 py-2">If Exceeded</th>
            <th class="px-4 py-2">Accounts</th>
            <th class="px-4 py-2">Status</th>
            <th class="px-4 py-2 text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="budget in budgets" :key="budget.id" class="border-t border-gray-100">
            <td class="px-4 py-2">{{ fiscalYearLabel(budget.fiscal_year_id) }}</td>
            <td class="px-4 py-2">{{ budget.action_if_annual_budget_exceeded }}</td>
            <td class="px-4 py-2">
              <div v-for="row in budget.accounts" :key="row.id" class="text-xs text-gray-600">
                {{ accountLabel(row.account_id) }}: {{ formatCurrency(row.budget_amount) }}
              </div>
            </td>
            <td class="px-4 py-2"><StatusBadge :status="docstatusLabel(budget.docstatus)" /></td>
            <td class="px-4 py-2 text-right">
              <button
                v-if="budget.docstatus === 0"
                class="text-xs font-medium text-primary hover:underline"
                @click="docAction(budget.id, 'submit')"
              >Submit</button>
              <button
                v-else-if="budget.docstatus === 1"
                class="text-xs font-medium text-red-600 hover:underline"
                @click="docAction(budget.id, 'cancel')"
              >Cancel</button>
            </td>
          </tr>
          <tr v-if="!budgets.length">
            <td colspan="5" class="px-4 py-8 text-center text-gray-400">No budgets yet.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
