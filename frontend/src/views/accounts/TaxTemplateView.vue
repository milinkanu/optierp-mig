<script setup lang="ts">
// Tax Templates: list/create/edit/delete sales & purchase Taxes & Charges
// templates. Backed by /tax-templates (GET/POST/PATCH/DELETE) + /tax-categories.
// Editing a template never rewrites posted documents (they copy rows at creation).

import { computed, onMounted, ref, watch } from "vue";
import { api } from "@/api/client";
import { useAccountsStore } from "@/stores/accounts";
import type { AccountNode, ErrorEnvelope } from "@/types/core";
import type { TaxTemplate } from "@/types/accounts";

interface TaxCategoryInfo {
  id: string;
  title: string;
}
interface TaxRowForm {
  charge_type: string;
  rate: number;
  account_head_id: string;
  description: string;
  add_deduct_tax: string;
  category: string;
}

const CHARGE_TYPES = [
  "On Net Total", "Actual", "On Previous Row Amount", "On Previous Row Total", "On Item Quantity",
];

function blankRow(): TaxRowForm {
  return { charge_type: "On Net Total", rate: 0, account_head_id: "", description: "", add_deduct_tax: "Add", category: "Total" };
}

const store = useAccountsStore();

const kind = ref<"sales" | "purchase">("sales");
const templates = ref<TaxTemplate[]>([]);
const taxCategories = ref<TaxCategoryInfo[]>([]);
const error = ref<ErrorEnvelope | null>(null);
const loading = ref(false);
const openId = ref<string | null>(null);

const showForm = ref(false);
const saving = ref(false);
const editId = ref<string | null>(null);
const form = ref({ title: "", is_default: false, tax_category_id: "", inclusive: false });
const rows = ref<TaxRowForm[]>([blankRow()]);

const accountName = computed(() => {
  const byId = new Map(store.accounts.map((a: AccountNode) => [a.id, a.account_name]));
  return (id: string): string => byId.get(id) ?? id;
});

function newRow(): void {
  rows.value.push(blankRow());
}
function removeRow(i: number): void {
  rows.value.splice(i, 1);
}

function openNew(): void {
  editId.value = null;
  form.value = { title: "", is_default: false, tax_category_id: "", inclusive: false };
  rows.value = [blankRow()];
  showForm.value = true;
}

function openEdit(t: TaxTemplate): void {
  editId.value = t.id;
  kind.value = (t.kind as "sales" | "purchase");
  form.value = {
    title: t.title,
    is_default: t.is_default,
    tax_category_id: t.tax_category_id ?? "",
    inclusive: t.details.some((d) => d.included_in_print_rate),
  };
  rows.value = t.details.map((d) => ({
    charge_type: d.charge_type,
    rate: Number(d.rate),
    account_head_id: d.account_head_id,
    description: d.description ?? "",
    add_deduct_tax: d.add_deduct_tax,
    category: d.category,
  }));
  if (!rows.value.length) rows.value = [blankRow()];
  showForm.value = true;
}

async function fetchTemplates(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const resp = await api.get<TaxTemplate[]>("/tax-templates", { params: { kind: kind.value } });
    templates.value = resp.data;
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    loading.value = false;
  }
}

async function save(): Promise<void> {
  saving.value = true;
  error.value = null;
  const details = rows.value
    .filter((r) => r.account_head_id)
    .map((r, idx) => ({
      charge_type: r.charge_type,
      rate: Number(r.rate),
      account_head_id: r.account_head_id,
      description: r.description || null,
      add_deduct_tax: r.add_deduct_tax,
      category: r.category,
      included_in_print_rate: form.value.inclusive,
      row_id: idx + 1,
    }));
  try {
    if (editId.value) {
      await api.patch(`/tax-templates/${editId.value}`, {
        title: form.value.title,
        is_default: form.value.is_default,
        tax_category_id: form.value.tax_category_id || null,
        details,
      });
    } else {
      await api.post("/tax-templates", {
        title: form.value.title,
        kind: kind.value,
        is_default: form.value.is_default,
        tax_category_id: form.value.tax_category_id || null,
        details,
      });
    }
    showForm.value = false;
    await fetchTemplates();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    saving.value = false;
  }
}

async function removeTemplate(t: TaxTemplate): Promise<void> {
  if (!window.confirm(`Delete tax template "${t.title}"? Posted documents keep their own tax rows.`)) return;
  error.value = null;
  try {
    await api.delete(`/tax-templates/${t.id}`);
    await fetchTemplates();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

watch(kind, () => {
  showForm.value = false;
  openId.value = null;
  void fetchTemplates();
});

onMounted(async () => {
  await Promise.all([
    store.fetchAccounts(),
    fetchTemplates(),
    api.get<TaxCategoryInfo[]>("/tax-categories").then((r) => (taxCategories.value = r.data)).catch(() => {}),
  ]);
});
</script>

<template>
  <div class="max-w-4xl">
    <div class="mb-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">Taxes &amp; Charges Templates</h1>
        <p class="text-sm text-gray-500">
          Reusable tax sets (e.g. GST 18%) picked on invoices. CGST + SGST is two rows of 9%.
        </p>
      </div>
      <button class="btn-primary" @click="showForm ? (showForm = false) : openNew()">
        {{ showForm ? "Close" : "New Template" }}
      </button>
    </div>

    <div class="mb-4 inline-flex rounded-lg bg-gray-100 p-1 text-sm">
      <button
        v-for="k in (['sales', 'purchase'] as const)"
        :key="k"
        class="rounded-md px-3 py-1 capitalize"
        :class="kind === k ? 'bg-white text-primary shadow-sm' : 'text-gray-600'"
        @click="kind = k"
      >{{ k }}</button>
    </div>

    <p v-if="error" class="mb-3 text-sm text-red-600">{{ error.detail }}</p>

    <form v-if="showForm" class="mb-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm" @submit.prevent="save">
      <p class="mb-3 text-sm text-gray-600">
        {{ editId ? "Editing" : "New" }} <span class="font-semibold capitalize">{{ kind }}</span> template
      </p>
      <div class="grid grid-cols-3 gap-4">
        <div>
          <label class="form-label">Title*</label>
          <input v-model="form.title" required class="form-input" :placeholder="`e.g. GST 18% (${kind})`" />
        </div>
        <div>
          <label class="form-label">Tax Category</label>
          <select v-model="form.tax_category_id" class="form-input">
            <option value="">— none —</option>
            <option v-for="c in taxCategories" :key="c.id" :value="c.id">{{ c.title }}</option>
          </select>
        </div>
        <label class="flex items-end gap-2 pb-2 text-sm text-gray-700">
          <input v-model="form.is_default" type="checkbox" />
          Default for {{ kind }}
        </label>
      </div>
      <label class="mt-3 flex items-center gap-2 text-sm text-gray-700">
        <input v-model="form.inclusive" type="checkbox" />
        Prices are tax-inclusive (MRP) — the engine back-calculates the net rate
      </label>

      <div class="mt-4">
        <div class="mb-2 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-gray-900">Tax Rows</h2>
          <button type="button" class="btn-secondary" @click="newRow">Add Row</button>
        </div>
        <div v-for="(row, i) in rows" :key="i" class="mb-2 grid grid-cols-12 gap-2">
          <select v-model="row.charge_type" class="form-input col-span-3">
            <option v-for="ct in CHARGE_TYPES" :key="ct" :value="ct">{{ ct }}</option>
          </select>
          <input v-model.number="row.rate" type="number" step="any" placeholder="Rate %" class="form-input col-span-1" />
          <select v-model="row.account_head_id" class="form-input col-span-3">
            <option value="" disabled>Account head…</option>
            <option v-for="a in store.leafAccounts" :key="a.id" :value="a.id">{{ a.account_name }}</option>
          </select>
          <input v-model="row.description" placeholder="Description" class="form-input col-span-2" />
          <select v-model="row.add_deduct_tax" class="form-input col-span-1">
            <option>Add</option>
            <option>Deduct</option>
          </select>
          <div class="col-span-2 flex gap-1">
            <select v-if="kind === 'purchase'" v-model="row.category" class="form-input flex-1">
              <option>Total</option>
              <option>Valuation</option>
              <option>Valuation and Total</option>
            </select>
            <button type="button" class="px-1 text-gray-400 hover:text-red-600" @click="removeRow(i)">✕</button>
          </div>
        </div>
      </div>

      <div class="mt-4 flex justify-end">
        <button type="submit" class="btn-primary" :disabled="saving || !form.title">
          {{ saving ? "Saving…" : editId ? "Save Changes" : "Save Template" }}
        </button>
      </div>
    </form>

    <div class="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      <table class="min-w-full text-sm">
        <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
          <tr>
            <th class="px-4 py-2">Title</th>
            <th class="px-4 py-2">Rows</th>
            <th class="px-4 py-2">Default</th>
            <th class="px-4 py-2 text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="t in templates" :key="t.id">
            <tr class="border-t border-gray-100 hover:bg-gray-50">
              <td class="cursor-pointer px-4 py-2 font-medium text-gray-900" @click="openId = openId === t.id ? null : t.id">
                {{ t.title }}
                <span v-if="t.details.some((d) => d.included_in_print_rate)" class="ml-1 rounded bg-blue-100 px-1.5 text-[10px] uppercase text-blue-700">incl</span>
              </td>
              <td class="px-4 py-2 text-gray-500">{{ t.details.length }}</td>
              <td class="px-4 py-2">
                <span v-if="t.is_default" class="rounded bg-green-100 px-1.5 text-[10px] uppercase text-green-700">default</span>
              </td>
              <td class="px-4 py-2 text-right whitespace-nowrap">
                <button class="text-xs font-medium text-gray-500 hover:underline" @click="openEdit(t)">Edit</button>
                <button class="ml-3 text-xs font-medium text-red-600 hover:underline" @click="removeTemplate(t)">Delete</button>
              </td>
            </tr>
            <tr v-if="openId === t.id" class="border-t border-gray-100 bg-gray-50">
              <td colspan="4" class="px-4 py-2">
                <table class="min-w-full text-xs">
                  <thead class="text-left text-gray-400">
                    <tr><th class="py-1 pr-4">Charge Type</th><th class="py-1 pr-4">Rate</th><th class="py-1 pr-4">Account</th><th class="py-1 pr-4">Add/Deduct</th><th class="py-1">Category</th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="(d, i) in t.details" :key="i" class="text-gray-600">
                      <td class="py-1 pr-4">{{ d.charge_type }}</td>
                      <td class="py-1 pr-4">{{ d.rate }}</td>
                      <td class="py-1 pr-4">{{ accountName(d.account_head_id) }}</td>
                      <td class="py-1 pr-4">{{ d.add_deduct_tax }}</td>
                      <td class="py-1">{{ d.category }}</td>
                    </tr>
                  </tbody>
                </table>
              </td>
            </tr>
          </template>
          <tr v-if="!templates.length">
            <td colspan="4" class="px-4 py-8 text-center text-gray-400">
              {{ loading ? "Loading…" : `No ${kind} templates yet.` }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
