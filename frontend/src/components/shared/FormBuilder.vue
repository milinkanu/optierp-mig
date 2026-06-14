<script setup lang="ts">
// Schema-driven form (Section 2.3 rule 5): every form is a config object,
// mirroring ERPNext's form metadata, enabling low-code customization later.

export interface FieldOption {
  value: string;
  label: string;
}

export interface FieldConfig {
  name: string;
  label: string;
  type: "text" | "password" | "email" | "number" | "date" | "select" | "checkbox" | "textarea" | "link";
  required?: boolean;
  placeholder?: string;
  options?: FieldOption[];
  link?: string; // for type "link": the target DocType slug (resolved to options by the form)
  span?: 1 | 2; // grid columns
  help?: string;
}

const props = defineProps<{
  fields: FieldConfig[];
  modelValue: Record<string, unknown>;
  errorField?: string | null;
}>();

const emit = defineEmits<{ "update:modelValue": [value: Record<string, unknown>] }>();

function setValue(name: string, value: unknown): void {
  emit("update:modelValue", { ...props.modelValue, [name]: value });
}

function onInput(field: FieldConfig, event: Event): void {
  const target = event.target as HTMLInputElement | HTMLSelectElement;
  if (field.type === "checkbox") {
    setValue(field.name, (target as HTMLInputElement).checked);
  } else if (field.type === "number") {
    setValue(field.name, target.value === "" ? null : Number(target.value));
  } else {
    setValue(field.name, target.value);
  }
}
</script>

<template>
  <div class="grid grid-cols-2 gap-4">
    <div
      v-for="field in fields"
      :key="field.name"
      :class="field.span === 2 ? 'col-span-2' : 'col-span-2 sm:col-span-1'"
    >
      <label :for="field.name" class="form-label">
        {{ field.label }}<span v-if="field.required" class="text-red-500">*</span>
      </label>

      <select
        v-if="field.type === 'select'"
        :id="field.name"
        class="form-input"
        :class="{ 'border-red-500': errorField === field.name }"
        :value="(modelValue[field.name] as string) ?? ''"
        @change="onInput(field, $event)"
      >
        <option value="" disabled>{{ field.placeholder ?? "Select…" }}</option>
        <option v-for="opt in field.options" :key="opt.value" :value="opt.value">
          {{ opt.label }}
        </option>
      </select>

      <input
        v-else-if="field.type === 'checkbox'"
        :id="field.name"
        type="checkbox"
        class="h-4 w-4 rounded border-gray-300 text-primary"
        :checked="Boolean(modelValue[field.name])"
        @change="onInput(field, $event)"
      />

      <textarea
        v-else-if="field.type === 'textarea'"
        :id="field.name"
        rows="3"
        class="form-input"
        :class="{ 'border-red-500': errorField === field.name }"
        :placeholder="field.placeholder"
        :value="(modelValue[field.name] as string | null) ?? ''"
        @input="onInput(field, $event)"
      />

      <input
        v-else
        :id="field.name"
        :type="field.type"
        class="form-input"
        :class="{ 'border-red-500': errorField === field.name }"
        :placeholder="field.placeholder"
        :value="(modelValue[field.name] as string | number | null) ?? ''"
        @input="onInput(field, $event)"
      />

      <p v-if="field.help" class="mt-1 text-xs text-gray-500">{{ field.help }}</p>
    </div>
  </div>
</template>
