<script setup lang="ts">
// Editable child-table grid (line items) for the metadata engine. Renders one
// column per child field and add/remove row controls. Link fields are resolved
// to selects (with options) by the parent form before being passed in.

import type { FieldConfig } from "@/components/shared/FormBuilder.vue";

type Row = Record<string, unknown>;

const props = defineProps<{
  label: string;
  fields: FieldConfig[];
  modelValue: Row[];
}>();

const emit = defineEmits<{ "update:modelValue": [rows: Row[]] }>();

function setCell(rowIndex: number, name: string, value: unknown): void {
  emit(
    "update:modelValue",
    props.modelValue.map((r, i) => (i === rowIndex ? { ...r, [name]: value } : r)),
  );
}

function onCell(rowIndex: number, field: FieldConfig, event: Event): void {
  const target = event.target as HTMLInputElement | HTMLSelectElement;
  if (field.type === "checkbox") {
    setCell(rowIndex, field.name, (target as HTMLInputElement).checked);
  } else if (field.type === "number") {
    setCell(rowIndex, field.name, target.value === "" ? null : Number(target.value));
  } else {
    setCell(rowIndex, field.name, target.value);
  }
}

function addRow(): void {
  emit("update:modelValue", [...props.modelValue, {}]);
}
function removeRow(index: number): void {
  emit(
    "update:modelValue",
    props.modelValue.filter((_, i) => i !== index),
  );
}

function inputType(field: FieldConfig): string {
  if (field.type === "number") return "number";
  if (field.type === "date") return "date";
  return "text";
}
</script>

<template>
  <div class="mt-6">
    <div class="mb-2 text-sm font-semibold text-gray-700">{{ label }}</div>
    <div class="overflow-x-auto rounded-lg border border-gray-200">
      <table class="min-w-full divide-y divide-gray-200 text-sm">
        <thead class="bg-gray-50">
          <tr>
            <th
              v-for="f in fields"
              :key="f.name"
              class="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500"
            >
              {{ f.label }}<span v-if="f.required" class="text-red-500">*</span>
            </th>
            <th class="w-10 px-3 py-2"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          <tr v-if="modelValue.length === 0">
            <td :colspan="fields.length + 1" class="px-3 py-4 text-center text-gray-400">No rows</td>
          </tr>
          <tr v-for="(row, i) in modelValue" :key="i">
            <td v-for="f in fields" :key="f.name" class="px-3 py-1.5">
              <select
                v-if="f.type === 'select'"
                class="form-input py-1"
                :value="(row[f.name] as string) ?? ''"
                @change="onCell(i, f, $event)"
              >
                <option value="" disabled>Select…</option>
                <option v-for="o in f.options" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
              <input
                v-else-if="f.type === 'checkbox'"
                type="checkbox"
                class="h-4 w-4 rounded border-gray-300 text-primary"
                :checked="Boolean(row[f.name])"
                @change="onCell(i, f, $event)"
              />
              <input
                v-else
                :type="inputType(f)"
                class="form-input py-1"
                :value="(row[f.name] as string | number | null) ?? ''"
                @input="onCell(i, f, $event)"
              />
            </td>
            <td class="px-3 py-1.5 text-right">
              <button
                type="button"
                class="text-red-500 hover:text-red-700"
                title="Remove row"
                @click="removeRow(i)"
              >
                ✕
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <button type="button" class="mt-2 text-sm font-medium text-primary hover:underline" @click="addRow">
      + Add row
    </button>
  </div>
</template>
