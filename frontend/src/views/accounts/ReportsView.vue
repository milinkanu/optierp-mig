<script setup lang="ts">
// Financial reports: Trial Balance / P&L / Balance Sheet / AR / AP.

import { onMounted, ref } from "vue";
import { api } from "@/api/client";
import type { ErrorEnvelope, ListResponse } from "@/types/core";
import type { AgingRow, FiscalYearInfo, StatementRow, TrialBalanceRow } from "@/types/accounts";

type Tab = "trial-balance" | "profit-loss" | "balance-sheet" | "receivable" | "payable";
const tab = ref<Tab>("trial-balance");

const today = new Date().toISOString().slice(0, 10);
const yearStart = `${new Date().getFullYear()}-01-01`;
const fromDate = ref(yearStart);
const toDate = ref(today);
const asOf = ref(today);

const fiscalYears = ref<FiscalYearInfo[]>([]);
const fiscalYearId = ref("");

const tbRows = ref<TrialBalanceRow[]>([]);
const pl = ref<{ income: StatementRow[]; expenses: StatementRow[]; net_profit: string } | null>(null);
const bs = ref<{
  assets: StatementRow[]; liabilities: StatementRow[]; equity: StatementRow[];
  total_assets: string; total_liabilities: string; total_equity: string;
  provisional_profit_loss: string;
} | null>(null);
const aging = ref<AgingRow[]>([]);
const error = ref<ErrorEnvelope | null>(null);
const loading = ref(false);

async function run(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    if (tab.value === "trial-balance" && fiscalYearId.value) {
      tbRows.value = (
        await api.get<TrialBalanceRow[]>("/reports/trial-balance", {
          params: { fiscal_year_id: fiscalYearId.value },
        })
      ).data;
    } else if (tab.value === "profit-loss") {
      pl.value = (
        await api.get("/reports/profit-loss", {
          params: { from_date: fromDate.value, to_date: toDate.value },
        })
      ).data;
    } else if (tab.value === "balance-sheet") {
      bs.value = (await api.get("/reports/balance-sheet", { params: { as_of: asOf.value } })).data;
    } else {
      const endpoint = tab.value === "receivable" ? "accounts-receivable" : "accounts-payable";
      aging.value = (
        await api.get<AgingRow[]>(`/reports/${endpoint}`, { params: { as_of: asOf.value } })
      ).data;
    }
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    loading.value = false;
  }
}

function switchTab(t: Tab): void {
  tab.value = t;
  void run();
}

onMounted(async () => {
  // fiscal years come via the settings store of Module 02's backend; reuse companies COA call later
  try {
    const resp = await api.get<ListResponse<FiscalYearInfo>>("/fiscal-years", { params: {} });
    fiscalYears.value = resp.data.items;
  } catch {
    fiscalYears.value = [];
  }
  void run();
});

const tabs: Array<{ key: Tab; label: string }> = [
  { key: "trial-balance", label: "Trial Balance" },
  { key: "profit-loss", label: "Profit & Loss" },
  { key: "balance-sheet", label: "Balance Sheet" },
  { key: "receivable", label: "Receivable" },
  { key: "payable", label: "Payable" },
];
</script>

<template>
  <div>
    <h1 class="mb-4 text-xl font-semibold text-gray-900">Financial Reports</h1>

    <div class="mb-4 flex gap-1 rounded-lg bg-gray-100 p-1">
      <button
        v-for="t in tabs"
        :key="t.key"
        class="flex-1 rounded-md px-3 py-1.5 text-sm font-medium"
        :class="tab === t.key ? 'bg-white text-primary shadow-sm' : 'text-gray-600'"
        @click="switchTab(t.key)"
      >
        {{ t.label }}
      </button>
    </div>

    <div class="mb-4 flex items-end gap-3 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <template v-if="tab === 'trial-balance'">
        <div>
          <label class="form-label">Fiscal Year</label>
          <select v-model="fiscalYearId" class="form-input w-56">
            <option value="" disabled>Select…</option>
            <option v-for="fy in fiscalYears" :key="fy.id" :value="fy.id">{{ fy.year }}</option>
          </select>
        </div>
      </template>
      <template v-else-if="tab === 'profit-loss'">
        <div><label class="form-label">From</label><input v-model="fromDate" type="date" class="form-input" /></div>
        <div><label class="form-label">To</label><input v-model="toDate" type="date" class="form-input" /></div>
      </template>
      <template v-else>
        <div><label class="form-label">As of</label><input v-model="asOf" type="date" class="form-input" /></div>
      </template>
      <button class="btn-primary" :disabled="loading" @click="run">Run</button>
      <p v-if="error" class="text-sm text-red-600">{{ error.detail }}</p>
    </div>

    <!-- Trial Balance -->
    <div v-if="tab === 'trial-balance'" class="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      <table class="min-w-full text-sm">
        <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
          <tr>
            <th class="px-4 py-2">Account</th>
            <th class="px-4 py-2 text-right">Opening Dr</th><th class="px-4 py-2 text-right">Opening Cr</th>
            <th class="px-4 py-2 text-right">Debit</th><th class="px-4 py-2 text-right">Credit</th>
            <th class="px-4 py-2 text-right">Closing Dr</th><th class="px-4 py-2 text-right">Closing Cr</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in tbRows" :key="row.account_id" class="border-t border-gray-100">
            <td class="px-4 py-1.5" :style="{ paddingLeft: `${16 + (row.path.split('.').length - 1) * 14}px` }"
                :class="row.is_group ? 'font-semibold' : ''">{{ row.account_name }}</td>
            <td class="px-4 py-1.5 text-right">{{ row.opening_debit }}</td>
            <td class="px-4 py-1.5 text-right">{{ row.opening_credit }}</td>
            <td class="px-4 py-1.5 text-right">{{ row.debit }}</td>
            <td class="px-4 py-1.5 text-right">{{ row.credit }}</td>
            <td class="px-4 py-1.5 text-right">{{ row.closing_debit }}</td>
            <td class="px-4 py-1.5 text-right">{{ row.closing_credit }}</td>
          </tr>
          <tr v-if="!tbRows.length"><td colspan="7" class="px-4 py-8 text-center text-gray-400">
            Select a fiscal year and run.
          </td></tr>
        </tbody>
      </table>
    </div>

    <!-- P&L -->
    <div v-else-if="tab === 'profit-loss' && pl" class="grid grid-cols-2 gap-4">
      <div v-for="(rows, section) in { Income: pl.income, Expenses: pl.expenses }" :key="section"
           class="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <h2 class="mb-2 text-sm font-semibold text-gray-900">{{ section }}</h2>
        <div v-for="row in rows" :key="row.account_id ?? row.account_name"
             class="flex justify-between py-0.5 text-sm"
             :style="{ paddingLeft: `${row.indent * 12}px` }"
             :class="row.is_group ? 'font-semibold' : ''">
          <span>{{ row.account_name }}</span><span>{{ row.amount }}</span>
        </div>
      </div>
      <div class="col-span-2 rounded-lg border border-gray-200 bg-white p-4 text-right shadow-sm">
        <span class="text-sm text-gray-500">Net Profit:</span>
        <span class="ml-2 text-lg font-semibold text-gray-900">{{ pl.net_profit }}</span>
      </div>
    </div>

    <!-- Balance Sheet -->
    <div v-else-if="tab === 'balance-sheet' && bs" class="grid grid-cols-3 gap-4">
      <div v-for="(rows, section) in { Assets: bs.assets, Liabilities: bs.liabilities, Equity: bs.equity }"
           :key="section" class="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <h2 class="mb-2 text-sm font-semibold text-gray-900">{{ section }}</h2>
        <div v-for="row in rows" :key="row.account_id ?? row.account_name"
             class="flex justify-between py-0.5 text-sm"
             :style="{ paddingLeft: `${row.indent * 12}px` }"
             :class="row.is_group ? 'font-semibold' : ''">
          <span>{{ row.account_name }}</span><span>{{ row.amount }}</span>
        </div>
      </div>
      <div class="col-span-3 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <div class="flex justify-end gap-8 text-sm">
          <span>Assets: <strong>{{ bs.total_assets }}</strong></span>
          <span>Liabilities: <strong>{{ bs.total_liabilities }}</strong></span>
          <span>Equity: <strong>{{ bs.total_equity }}</strong></span>
          <span>Provisional P&amp;L: <strong>{{ bs.provisional_profit_loss }}</strong></span>
        </div>
      </div>
    </div>

    <!-- AR / AP aging -->
    <div v-else-if="tab === 'receivable' || tab === 'payable'"
         class="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      <table class="min-w-full text-sm">
        <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
          <tr>
            <th class="px-4 py-2">Party</th><th class="px-4 py-2">Voucher</th>
            <th class="px-4 py-2">Due</th><th class="px-4 py-2 text-right">Outstanding</th>
            <th class="px-4 py-2 text-right">0-30</th><th class="px-4 py-2 text-right">31-60</th>
            <th class="px-4 py-2 text-right">61-90</th><th class="px-4 py-2 text-right">90+</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in aging" :key="row.voucher_no" class="border-t border-gray-100">
            <td class="px-4 py-1.5">{{ row.party_name }}</td>
            <td class="px-4 py-1.5">{{ row.voucher_no }}</td>
            <td class="px-4 py-1.5">{{ row.due_date ?? row.posting_date }}</td>
            <td class="px-4 py-1.5 text-right">{{ row.outstanding_amount }}</td>
            <td class="px-4 py-1.5 text-right">{{ row.bucket_0_30 }}</td>
            <td class="px-4 py-1.5 text-right">{{ row.bucket_31_60 }}</td>
            <td class="px-4 py-1.5 text-right">{{ row.bucket_61_90 }}</td>
            <td class="px-4 py-1.5 text-right">{{ row.bucket_90_plus }}</td>
          </tr>
          <tr v-if="!aging.length"><td colspan="8" class="px-4 py-8 text-center text-gray-400">
            Nothing outstanding. 🎉
          </td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
