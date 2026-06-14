<script setup lang="ts">
// Generic form view — renders the create/edit form for ANY registered DocType
// from its /meta config, driving FormBuilder + useDocument. No per-doctype code.

import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "@/api/client";
import FormBuilder from "@/components/shared/FormBuilder.vue";
import { useDocument } from "@/composables/useDocument";
import type { DocTypeMeta } from "@/types/registry";

const route = useRoute();
const router = useRouter();

const doctype = route.params.doctype as string;
const idParam = route.params.id as string | undefined;
const isNew = !idParam || idParam === "new";

const meta = ref<DocTypeMeta | null>(null);
const model = ref<Record<string, unknown>>({});
const errorField = ref<string | null>(null);

const { doc, saving, error, load, create, update, remove } = useDocument<
  { id: string } & Record<string, unknown>
>(`/registry/${doctype}`);

onMounted(async () => {
  const m = (await api.get<DocTypeMeta>(`/meta/${doctype}`)).data;
  // Resolve Link fields into dropdowns by fetching the target's options.
  // Resilient: a field whose target the user can't read just stays an empty list.
  await Promise.all(
    m.fields
      .filter((f) => f.type === "link" && f.link)
      .map(async (f) => {
        try {
          f.options = (
            await api.get<{ value: string; label: string }[]>(`/registry/${f.link}/options`)
          ).data;
        } catch {
          f.options = [];
        }
        f.type = "select";
      }),
  );
  meta.value = m;
  if (!isNew && idParam) {
    await load(idParam);
    if (doc.value) model.value = { ...doc.value };
  }
});

async function destroy(): Promise<void> {
  if (!idParam || !confirm("Delete this record? This cannot be undone.")) return;
  if (await remove(idParam)) void router.push(`/m/${doctype}`);
}

async function save(): Promise<void> {
  errorField.value = null;
  const result = isNew ? await create(model.value) : await update(idParam as string, model.value);
  if (result) {
    void router.push(`/m/${doctype}`);
  } else {
    errorField.value = error.value?.field ?? null;
  }
}

function cancel(): void {
  void router.push(`/m/${doctype}`);
}
</script>

<template>
  <div class="mx-auto max-w-3xl">
    <h1 class="mb-4 text-xl font-semibold text-gray-900">
      {{ isNew ? "New" : "Edit" }} {{ meta?.name ?? "" }}
    </h1>

    <p v-if="error && !errorField" class="mb-3 text-sm text-red-600">{{ error.detail }}</p>

    <div v-if="meta" class="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <FormBuilder v-model="model" :fields="meta.fields" :error-field="errorField" />
      <div class="mt-6 flex items-center justify-between">
        <div class="flex gap-2">
          <button
            class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
            :disabled="saving"
            @click="save"
          >
            {{ saving ? "Saving…" : "Save" }}
          </button>
          <button
            class="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700"
            @click="cancel"
          >
            Cancel
          </button>
        </div>
        <button
          v-if="!isNew"
          class="rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
          :disabled="saving"
          @click="destroy"
        >
          Delete
        </button>
      </div>
    </div>
  </div>
</template>
