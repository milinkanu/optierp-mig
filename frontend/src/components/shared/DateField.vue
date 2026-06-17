<script setup lang="ts">
// Date input that displays/accepts dd-mm-yyyy (ERPNext-India style) while
// storing ISO yyyy-mm-dd via v-model. Stays typeable and keeps a native
// calendar picker (opened from the icon), since a native <input type="date">
// is locale-locked to the browser's format.

import { ref, watch } from "vue";

const props = defineProps<{ modelValue: string; required?: boolean }>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();

const native = ref<HTMLInputElement | null>(null);
const text = ref(toDisplay(props.modelValue));

watch(
  () => props.modelValue,
  (v) => {
    text.value = toDisplay(v);
  },
);

function toDisplay(iso: string): string {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return y && m && d ? `${d}-${m}-${y}` : "";
}

function parse(s: string): string | null {
  const m = s.trim().match(/^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$/);
  if (!m) return null;
  const [, d, mo, y] = m;
  const iso = `${y}-${mo.padStart(2, "0")}-${d.padStart(2, "0")}`;
  const dt = new Date(iso);
  return Number.isNaN(dt.getTime()) ? null : iso;
}

function commit(): void {
  if (text.value.trim() === "") {
    emit("update:modelValue", "");
    return;
  }
  const iso = parse(text.value);
  if (iso) emit("update:modelValue", iso);
  else text.value = toDisplay(props.modelValue); // revert invalid input
}

function openPicker(): void {
  native.value?.showPicker?.();
}

function onPick(event: Event): void {
  emit("update:modelValue", (event.target as HTMLInputElement).value);
}
</script>

<template>
  <div class="relative">
    <input
      type="text"
      class="form-input pr-9"
      :value="text"
      :required="required"
      placeholder="dd-mm-yyyy"
      inputmode="numeric"
      @input="text = ($event.target as HTMLInputElement).value"
      @change="commit"
      @blur="commit"
    />
    <button
      type="button"
      tabindex="-1"
      class="absolute inset-y-0 right-0 flex items-center px-2 text-gray-400 hover:text-gray-600"
      title="Open calendar"
      @click="openPicker"
    >
      📅
    </button>
    <!-- native picker, overlaid + transparent so the text field stays usable -->
    <input
      ref="native"
      type="date"
      tabindex="-1"
      class="pointer-events-none absolute inset-0 opacity-0"
      :value="modelValue"
      @input="onPick"
    />
  </div>
</template>
