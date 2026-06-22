<script setup lang="ts">
// Subscriptions: attach billing plan(s) to a customer; a daily job (or the "Generate
// invoice now" action here) turns each cycle into a real, submitted Sales Invoice.
// Idempotent — generating twice for the same period does nothing the second time.
import { onMounted, ref } from "vue";
import { api } from "@/api/client";
import { useAccountsStore } from "@/stores/accounts";
import { formatDate } from "@/utils/format";
import StatusBadge from "@/components/shared/StatusBadge.vue";
import type { ErrorEnvelope, ListResponse } from "@/types/core";

interface SubscriptionRow {
  id: string;
  name: string;
  customer_name: string | null;
  status: string;
  start_date: string;
  end_date: string | null;
  next_invoice_date: string;
}

interface PlanOption {
  id: string;
  plan_name: string;
  billing_interval: string;
  interval_count: number;
  price: string;
}

interface PlanLine {
  plan_id: string;
  qty: number;
}

interface GenerateResult {
  generated: boolean;
  invoice_name: string | null;
  detail: string | null;
}

const store = useAccountsStore();

const rows = ref<SubscriptionRow[]>([]);
const plans = ref<PlanOption[]>([]);
const loading = ref(false);
const error = ref<ErrorEnvelope | null>(null);
const notice = ref<string | null>(null);

const showForm = ref(false);
const today = new Date().toISOString().slice(0, 10);
const fCustomer = ref("");
const fStart = ref(today);
const fEnd = ref("");
const fDaysUntilDue = ref<number>(0);
const fGenerateAt = ref<"Beginning" | "End">("Beginning");
const fLines = ref<PlanLine[]>([{ plan_id: "", qty: 1 }]);
const saving = ref(false);

function addLine(): void {
  fLines.value.push({ plan_id: "", qty: 1 });
}
function removeLine(i: number): void {
  fLines.value.splice(i, 1);
  if (!fLines.value.length) addLine();
}

async function fetchPlans(): Promise<void> {
  try {
    plans.value = (
      await api.get<ListResponse<PlanOption>>("/registry/subscription-plan", {
        params: { page_size: 200 },
      })
    ).data.items;
  } catch {
    plans.value = [];
  }
}

async function fetchList(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    rows.value = (
      await api.get<ListResponse<SubscriptionRow>>("/subscriptions", { params: { page_size: 100 } })
    ).data.items;
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    loading.value = false;
  }
}

async function save(): Promise<void> {
  const lines = fLines.value.filter((l) => l.plan_id);
  if (!fCustomer.value || !lines.length) return;
  saving.value = true;
  error.value = null;
  try {
    await api.post("/subscriptions", {
      customer_id: fCustomer.value,
      start_date: fStart.value,
      end_date: fEnd.value || null,
      days_until_due: fDaysUntilDue.value || 0,
      generate_at: fGenerateAt.value,
      plans: lines.map((l) => ({ plan_id: l.plan_id, qty: l.qty })),
    });
    showForm.value = false;
    fCustomer.value = "";
    fStart.value = today;
    fEnd.value = "";
    fDaysUntilDue.value = 0;
    fGenerateAt.value = "Beginning";
    fLines.value = [{ plan_id: "", qty: 1 }];
    await fetchList();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    saving.value = false;
  }
}

async function generate(row: SubscriptionRow): Promise<void> {
  notice.value = null;
  error.value = null;
  try {
    const res = (await api.post<GenerateResult>(`/subscriptions/${row.id}/generate-invoice`)).data;
    notice.value = res.generated
      ? `${row.name}: generated invoice ${res.invoice_name}.`
      : `${row.name}: nothing generated — ${res.detail}.`;
    await fetchList();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

async function cancel(row: SubscriptionRow): Promise<void> {
  error.value = null;
  try {
    await api.post(`/subscriptions/${row.id}/cancel`);
    await fetchList();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

onMounted(async () => {
  await Promise.all([store.fetchCustomers(), fetchPlans(), fetchList()]);
});
</script>

<template>
  <div>
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">Subscriptions</h1>
        <p class="text-sm text-gray-500">
          Recurring billing (AMC, rentals, retainers). Attach a billing plan to a customer; each cycle
          becomes a real Sales Invoice automatically. Generating is idempotent — it never double-bills a
          period. Define plans under
          <RouterLink to="/m/subscription-plan" class="text-blue-600 hover:underline">Subscription Plan</RouterLink>.
        </p>
      </div>
      <button class="btn-primary" @click="showForm = !showForm">
        {{ showForm ? "Close" : "New Subscription" }}
      </button>
    </div>

    <p v-if="notice" class="mb-3 rounded bg-green-50 px-3 py-2 text-sm text-green-700">{{ notice }}</p>

    <form
      v-if="showForm"
      class="mb-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm"
      @submit.prevent="save"
    >
      <div class="grid grid-cols-2 gap-4 md:grid-cols-4">
        <div>
          <label class="form-label">Customer*</label>
          <select v-model="fCustomer" required class="form-input">
            <option value="" disabled>Select…</option>
            <option v-for="c in store.customers" :key="c.id" :value="c.id">{{ c.customer_name }}</option>
          </select>
        </div>
        <div>
          <label class="form-label">Start / first invoice*</label>
          <input v-model="fStart" type="date" required class="form-input" />
        </div>
        <div>
          <label class="form-label">End date</label>
          <input v-model="fEnd" type="date" class="form-input" />
        </div>
        <div>
          <label class="form-label">Due in (days)</label>
          <input v-model.number="fDaysUntilDue" type="number" min="0" class="form-input" />
        </div>
        <div>
          <label class="form-label">Bill at</label>
          <select v-model="fGenerateAt" class="form-input">
            <option value="Beginning">Beginning of period</option>
            <option value="End">End of period</option>
          </select>
        </div>
      </div>

      <div class="mt-4">
        <label class="form-label">Plans*</label>
        <div v-for="(line, i) in fLines" :key="i" class="mb-2 flex items-center gap-2">
          <select v-model="line.plan_id" class="form-input flex-1">
            <option value="" disabled>Select a plan…</option>
            <option v-for="p in plans" :key="p.id" :value="p.id">
              {{ p.plan_name }} — every {{ p.interval_count }} {{ p.billing_interval.toLowerCase() }}(s)
            </option>
          </select>
          <input v-model.number="line.qty" type="number" min="1" step="any" class="form-input w-24" placeholder="Qty" />
          <button type="button" class="text-sm text-red-600 hover:underline" @click="removeLine(i)">remove</button>
        </div>
        <button type="button" class="text-sm text-blue-600 hover:underline" @click="addLine">+ add plan</button>
        <p v-if="!plans.length" class="mt-1 text-xs text-amber-600">
          No plans yet — create one under Subscription Plan first.
        </p>
      </div>

      <p v-if="error" class="mt-2 text-sm text-red-600">{{ error.detail }}</p>
      <div class="mt-4 flex justify-end">
        <button type="submit" class="btn-primary" :disabled="saving || !fCustomer">
          {{ saving ? "Saving…" : "Create" }}
        </button>
      </div>
    </form>

    <div class="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      <table class="min-w-full text-sm">
        <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
          <tr>
            <th class="px-4 py-2">Subscription</th><th class="px-4 py-2">Customer</th>
            <th class="px-4 py-2">Next invoice</th><th class="px-4 py-2">Period</th>
            <th class="px-4 py-2">Status</th><th class="px-4 py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id" class="border-t border-gray-100">
            <td class="px-4 py-1.5 font-medium text-gray-900">{{ row.name }}</td>
            <td class="px-4 py-1.5">{{ row.customer_name ?? "—" }}</td>
            <td class="px-4 py-1.5 text-gray-500">{{ formatDate(row.next_invoice_date) }}</td>
            <td class="px-4 py-1.5 text-gray-500">
              {{ formatDate(row.start_date) }} → {{ row.end_date ? formatDate(row.end_date) : "open" }}
            </td>
            <td class="px-4 py-1.5"><StatusBadge :status="row.status" /></td>
            <td class="px-4 py-1.5">
              <div class="flex flex-wrap items-center gap-2">
                <button
                  v-if="row.status === 'Active' || row.status === 'Past Due'"
                  class="text-xs text-green-700 hover:underline"
                  @click="generate(row)"
                >
                  generate invoice now
                </button>
                <button
                  v-if="row.status === 'Active' || row.status === 'Past Due'"
                  class="text-xs text-red-600 hover:underline"
                  @click="cancel(row)"
                >
                  cancel
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="!rows.length && !loading">
            <td colspan="6" class="px-4 py-8 text-center text-gray-400">
              No subscriptions yet. Create one to start recurring billing.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
