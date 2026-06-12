<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import FormBuilder, { type FieldConfig } from "@/components/shared/FormBuilder.vue";
import { useDocument } from "@/composables/useDocument";
import { useCoreStore } from "@/stores/core";
import type { User } from "@/types/core";

const router = useRouter();
const core = useCoreStore();
const { error, saving, create } = useDocument<User>("/users");

const form = ref<Record<string, unknown>>({});
const selectedRoles = ref<string[]>([]);

const fields = computed<FieldConfig[]>(() => [
  { name: "email", label: "Email", type: "email", required: true, span: 2 },
  { name: "first_name", label: "First Name", type: "text", required: true },
  { name: "last_name", label: "Last Name", type: "text" },
  { name: "password", label: "Password", type: "password", required: true, help: "Min. 8 characters" },
  {
    name: "default_company_id",
    label: "Default Company",
    type: "select",
    options: core.companies.map((c) => ({ value: c.id, label: c.company_name })),
  },
]);

function toggleRole(role: string): void {
  const idx = selectedRoles.value.indexOf(role);
  if (idx >= 0) selectedRoles.value.splice(idx, 1);
  else selectedRoles.value.push(role);
}

async function submit(): Promise<void> {
  const created = await create({ ...form.value, roles: selectedRoles.value });
  if (created) void router.push({ name: "users" });
}

onMounted(() => {
  void core.fetchRoles();
  void core.fetchCompanies();
});
</script>

<template>
  <div class="max-w-3xl">
    <h1 class="mb-4 text-xl font-semibold text-gray-900">New User</h1>
    <form class="rounded-lg border border-gray-200 bg-white p-6 shadow-sm" @submit.prevent="submit">
      <FormBuilder v-model="form" :fields="fields" :error-field="error?.field" />

      <div class="mt-4">
        <span class="form-label">Roles</span>
        <div class="mt-1 grid grid-cols-2 gap-2 sm:grid-cols-3">
          <label
            v-for="role in core.roles"
            :key="role.name"
            class="flex items-center gap-2 rounded-md border border-gray-200 px-3 py-2 text-sm"
            :class="selectedRoles.includes(role.name) ? 'border-primary bg-primary/5' : ''"
          >
            <input
              type="checkbox"
              class="h-4 w-4 rounded border-gray-300 text-primary"
              :checked="selectedRoles.includes(role.name)"
              @change="toggleRole(role.name)"
            />
            {{ role.name }}
          </label>
        </div>
      </div>

      <p v-if="error" class="mt-3 text-sm text-red-600">{{ error.detail }}</p>
      <div class="mt-6 flex justify-end gap-3">
        <button type="button" class="btn-secondary" @click="router.back()">Cancel</button>
        <button type="submit" class="btn-primary" :disabled="saving">
          {{ saving ? "Creating…" : "Create User" }}
        </button>
      </div>
    </form>
  </div>
</template>
