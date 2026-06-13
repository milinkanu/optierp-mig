<script setup lang="ts">
// Landing page: live financial snapshot for the active company.

import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useCompanyCurrency } from "@/composables/useCompanyCurrency";
import { formatCurrency, formatDate } from "@/utils/format";
import type { ListResponse } from "@/types/core";
import type { AgingRow, FiscalYearInfo, InvoiceListItem } from "@/types/accounts";

const auth = useAuthStore();
const router = useRouter();
const companyCurrency = useCompanyCurrency();

const receivables = ref<AgingRow[]>([]);
const payables = ref<AgingRow[]>([]);
const netProfit = ref<string | null>(null);
const recentInvoices = ref<InvoiceListItem[]>([]);
const fiscalYearLabel = ref("");
const loaded = ref(false);

const totalReceivable = computed(() =>
  receivables.value.reduce((sum, r) => sum + Number(r.outstanding_amount), 0),
);
const totalPayable = computed(() =>
  payables.value.reduce((sum, r) => sum + Number(r.outstanding_amount), 0),
);
// matches the list's Overdue status: only invoices WITH a due date that passed
const overdueCount = computed(
  () => receivables.value.filter((r) => r.due_date !== null && r.age_days > 0).length,
);

onMounted(async () => {
  // each card degrades independently if a permission/report call fails
  const [ar, ap, recent, fys] = await Promise.allSettled([
    api.get<AgingRow[]>("/reports/accounts-receivable"),
    api.get<AgingRow[]>("/reports/accounts-payable"),
    api.get<ListResponse<InvoiceListItem>>("/sales-invoices", { params: { page_size: 6 } }),
    api.get<ListResponse<FiscalYearInfo>>("/fiscal-years"),
  ]);
  if (ar.status === "fulfilled") receivables.value = ar.value.data;
  if (ap.status === "fulfilled") payables.value = ap.value.data;
  if (recent.status === "fulfilled") recentInvoices.value = recent.value.data.items;

  const currentFy = fys.status === "fulfilled" ? fys.value.data.items[0] : undefined;
  if (currentFy) {
    fiscalYearLabel.value = currentFy.year;
    try {
      const pl = await api.get<{ net_profit: string }>("/reports/profit-loss", {
        params: { from_date: currentFy.year_start_date, to_date: new Date().toISOString().slice(0, 10) },
      });
      netProfit.value = pl.data.net_profit;
    } catch {
      netProfit.value = null;
    }
  }
  loaded.value = true;
});
</script>

<template>
  <div>
    <h1 class="text-2xl font-semibold text-gray-900">Welcome, {{ auth.fullName }}</h1>
    <p class="mt-1 text-sm text-gray-500">Here's how the business looks today.</p>

    <div class="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <button class="rounded-lg border border-gray-200 bg-white p-5 text-left shadow-sm hover:border-primary/40"
              @click="router.push({ name: 'reports' })">
        <div class="text-sm text-gray-500">To Collect (Receivables)</div>
        <div class="mt-1 text-2xl font-semibold text-gray-900">{{ formatCurrency(totalReceivable, companyCurrency) }}</div>
        <div class="mt-1 text-xs text-gray-400">{{ receivables.length }} open invoice(s)</div>
      </button>
      <button class="rounded-lg border border-gray-200 bg-white p-5 text-left shadow-sm hover:border-primary/40"
              @click="router.push({ name: 'reports' })">
        <div class="text-sm text-gray-500">To Pay (Payables)</div>
        <div class="mt-1 text-2xl font-semibold text-gray-900">{{ formatCurrency(totalPayable, companyCurrency) }}</div>
        <div class="mt-1 text-xs text-gray-400">{{ payables.length }} open bill(s)</div>
      </button>
      <button class="rounded-lg border border-gray-200 bg-white p-5 text-left shadow-sm hover:border-primary/40"
              @click="router.push({ name: 'sales-invoices', query: { status: 'Overdue' } })">
        <div class="text-sm text-gray-500">Overdue Invoices</div>
        <div class="mt-1 text-2xl font-semibold" :class="overdueCount ? 'text-red-600' : 'text-gray-900'">
          {{ overdueCount }}
        </div>
        <div class="mt-1 text-xs text-gray-400">past their due date</div>
      </button>
      <button class="rounded-lg border border-gray-200 bg-white p-5 text-left shadow-sm hover:border-primary/40"
              @click="router.push({ name: 'reports' })">
        <div class="text-sm text-gray-500">Net Profit {{ fiscalYearLabel ? `(FY ${fiscalYearLabel})` : "" }}</div>
        <div class="mt-1 text-2xl font-semibold"
             :class="Number(netProfit ?? 0) >= 0 ? 'text-green-700' : 'text-red-600'">
          {{ netProfit !== null ? formatCurrency(netProfit, companyCurrency) : "—" }}
        </div>
        <div class="mt-1 text-xs text-gray-400">year to date</div>
      </button>
    </div>

    <div class="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div class="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm lg:col-span-2">
        <div class="flex items-center justify-between border-b border-gray-100 px-5 py-3">
          <h2 class="text-sm font-semibold text-gray-900">Recent Sales Invoices</h2>
          <RouterLink :to="{ name: 'sales-invoices' }" class="text-sm text-primary hover:underline">
            View all →
          </RouterLink>
        </div>
        <table class="min-w-full text-sm">
          <tbody>
            <tr v-for="invoice in recentInvoices" :key="invoice.id"
                class="cursor-pointer border-b border-gray-50 hover:bg-gray-50"
                @click="router.push(`/sales-invoices/${invoice.id}`)">
              <td class="px-5 py-2.5 font-medium text-gray-900">{{ invoice.name }}</td>
              <td class="px-5 py-2.5">{{ invoice.customer_name ?? "—" }}</td>
              <td class="px-5 py-2.5 text-gray-500">{{ formatDate(invoice.posting_date) }}</td>
              <td class="px-5 py-2.5 text-right">{{ formatCurrency(invoice.grand_total, invoice.currency ?? companyCurrency) }}</td>
              <td class="px-5 py-2.5"><StatusBadge :status="invoice.status" /></td>
            </tr>
            <tr v-if="loaded && !recentInvoices.length">
              <td colspan="5" class="px-5 py-8 text-center text-gray-400">No invoices yet — create your first one.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <h2 class="mb-3 text-sm font-semibold text-gray-900">Quick Actions</h2>
        <div class="space-y-2">
          <button class="btn-primary w-full" @click="router.push('/sales-invoices/new')">New Sales Invoice</button>
          <button class="btn-secondary w-full" @click="router.push('/purchase-invoices/new')">New Purchase Invoice</button>
          <button class="btn-secondary w-full" @click="router.push({ name: 'payment-entries' })">Record a Payment</button>
          <button class="btn-secondary w-full" @click="router.push({ name: 'payment-reconciliation' })">Reconcile Payments</button>
        </div>
        <div class="mt-4 border-t border-gray-100 pt-3">
          <div class="text-xs text-gray-400">Your roles</div>
          <div class="mt-1 flex flex-wrap gap-1">
            <span v-for="role in auth.roles" :key="role"
                  class="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
              {{ role }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
