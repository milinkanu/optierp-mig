<script setup lang="ts">
// Inline manager for a linked DocType (e.g. a Customer's Addresses / Contacts).
// Lists records that point at the parent via `link.link_field`, with add / edit
// / delete handled in-place — so Customer, Address and Contact are managed in
// one screen. Driven entirely by the linked DocType's /meta (no per-type code).

import { computed, onMounted, ref } from "vue";
import { api } from "@/api/client";
import FormBuilder, { type FieldConfig } from "@/components/shared/FormBuilder.vue";
import type { DocTypeMeta, MetaLink } from "@/types/registry";
import type { ErrorEnvelope } from "@/types/core";

const props = defineProps<{ parentId: string; link: MetaLink }>();

type Rec = { id: string } & Record<string, unknown>;

const childMeta = ref<DocTypeMeta | null>(null);
const records = ref<Rec[]>([]);
const loaded = ref(false);

const showForm = ref(false);
const editing = ref<Record<string, unknown>>({});
const editId = ref<string | null>(null);
const saving = ref(false);
const error = ref<ErrorEnvelope | null>(null);

const endpoint = computed(() => `/registry/${props.link.doctype}`);
// Fields shown in the inline editor — the FK back to the parent is set for you.
const formFields = computed<FieldConfig[]>(
  () => childMeta.value?.fields.filter((f) => f.name !== props.link.link_field) ?? [],
);

async function resolveLinks(fields: FieldConfig[]): Promise<void> {
  await Promise.all(
    fields
      .filter((f) => f.type === "link" && f.link)
      .map(async (f) => {
        try {
          f.options = (await api.get<{ value: string; label: string }[]>(`/registry/${f.link}/options`)).data;
        } catch {
          f.options = [];
        }
        f.type = "select";
      }),
  );
}

async function fetchRecords(): Promise<void> {
  try {
    const resp = await api.get<{ items: Rec[] }>(endpoint.value, { params: { page_size: 200 } });
    // Filter client-side to this parent (records carry the FK column).
    records.value = resp.data.items.filter((r) => r[props.link.link_field] === props.parentId);
  } catch {
    records.value = [];
  }
}

onMounted(async () => {
  try {
    const m = (await api.get<DocTypeMeta>(`/meta/${props.link.doctype}`)).data;
    await resolveLinks(m.fields);
    childMeta.value = m;
    await fetchRecords();
  } finally {
    loaded.value = true;
  }
});

function startAdd(): void {
  editing.value = {};
  editId.value = null;
  error.value = null;
  showForm.value = true;
}
function startEdit(rec: Rec): void {
  editing.value = { ...rec };
  editId.value = rec.id;
  error.value = null;
  showForm.value = true;
}
function cancelForm(): void {
  showForm.value = false;
}

async function saveRecord(): Promise<void> {
  saving.value = true;
  error.value = null;
  const payload = { ...editing.value, [props.link.link_field]: props.parentId };
  try {
    if (editId.value) await api.patch(`${endpoint.value}/${editId.value}`, payload);
    else await api.post(endpoint.value, payload);
    showForm.value = false;
    await fetchRecords();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    saving.value = false;
  }
}

async function removeRecord(rec: Rec): Promise<void> {
  if (!confirm(`Delete this ${childMeta.value?.name.toLowerCase() ?? "record"}?`)) return;
  try {
    await api.delete(`${endpoint.value}/${rec.id}`);
    await fetchRecords();
  } catch (e) {
    error.value = e as ErrorEnvelope;
  }
}

function title(rec: Rec): string {
  return String(rec[childMeta.value?.title_field ?? "name"] ?? "—");
}
function summary(rec: Rec): string {
  const cols = childMeta.value?.list_fields ?? [];
  return cols
    .map((c) => rec[c.key])
    .filter((v) => v !== null && v !== undefined && v !== "" && typeof v !== "boolean")
    .join(" · ");
}
</script>

<template>
  <div class="mt-6">
    <div class="mb-2 flex items-center justify-between">
      <h3 class="text-sm font-semibold text-gray-700">{{ link.label }}</h3>
      <button
        type="button"
        class="text-sm font-medium text-primary hover:underline"
        @click="startAdd"
      >
        + Add {{ childMeta?.name ?? "" }}
      </button>
    </div>

    <!-- record list -->
    <div v-if="records.length" class="divide-y divide-gray-100 rounded-lg border border-gray-200">
      <div v-for="rec in records" :key="rec.id" class="flex items-start justify-between gap-3 px-3 py-2">
        <div class="min-w-0">
          <div class="truncate text-sm font-medium text-gray-900">{{ title(rec) }}</div>
          <div v-if="summary(rec)" class="truncate text-xs text-gray-500">{{ summary(rec) }}</div>
        </div>
        <div class="flex shrink-0 gap-3 text-xs">
          <button type="button" class="text-primary hover:underline" @click="startEdit(rec)">Edit</button>
          <button type="button" class="text-red-500 hover:underline" @click="removeRecord(rec)">Delete</button>
        </div>
      </div>
    </div>
    <p v-else-if="loaded" class="rounded-lg border border-dashed border-gray-200 px-3 py-3 text-sm text-gray-400">
      No {{ link.label.toLowerCase() }} yet.
    </p>

    <!-- inline add / edit form -->
    <div v-if="showForm" class="mt-3 rounded-lg border border-primary/30 bg-gray-50 p-4">
      <div class="mb-2 text-sm font-medium text-gray-700">
        {{ editId ? "Edit" : "New" }} {{ childMeta?.name ?? "" }}
      </div>
      <FormBuilder v-model="editing" :fields="formFields" :error-field="error?.field ?? null" />
      <p v-if="error" class="mt-2 text-sm text-red-600">{{ error.detail }}</p>
      <div class="mt-3 flex gap-2">
        <button
          type="button"
          class="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          :disabled="saving"
          @click="saveRecord"
        >
          {{ saving ? "Saving…" : "Save" }}
        </button>
        <button
          type="button"
          class="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700"
          @click="cancelForm"
        >
          Cancel
        </button>
      </div>
    </div>
  </div>
</template>
