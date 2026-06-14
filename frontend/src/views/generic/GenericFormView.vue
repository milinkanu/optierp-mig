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

const { doc, saving, error, load, create, update } = useDocument<
  { id: string } & Record<string, unknown>
>(`/registry/${doctype}`);

onMounted(async () => {
  const m = (await api.get<DocTypeMeta>(`/meta/${doctype}`)).data;
  // Resolve Link fields into dropdowns by fetching the target's options.
  await Promise.all(
    m.fields
      .filter((f) => f.type === "link" && f.link)
      .map(async (f) => {
        f.options = (
          await api.get<{ value: string; label: string }[]>(`/registry/${f.link}/options`)
        ).data;
        f.type = "select";
      }),
  );
  meta.value = m;
  if (!isNew && idParam) {
    await load(idParam);
    if (doc.value) model.value = { ...doc.value };
  }
});

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
      <div class="mt-6 flex gap-2">
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
    </div>
  </div>
</template>
