<script setup lang="ts">
// Modal for entering a line's serial numbers (one per line). Shows a live count
// vs the required stock quantity so the user can see when it matches before saving.
import { computed, ref, watch } from "vue";

const props = defineProps<{ modelValue: string; required: number; title?: string }>();
const emit = defineEmits<{ "update:modelValue": [value: string]; close: [] }>();

const text = ref(props.modelValue ?? "");
watch(() => props.modelValue, (v) => { text.value = v ?? ""; });

const count = computed(
  () => text.value.split("\n").map((s) => s.trim()).filter(Boolean).length,
);
const matches = computed(() => count.value === props.required);

function done(): void {
  emit("update:modelValue", text.value);
  emit("close");
}
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
    @click.self="emit('close')"
  >
    <div class="w-full max-w-md rounded-lg bg-white p-5 shadow-xl">
      <h3 class="mb-1 text-sm font-semibold text-gray-900">{{ title || "Serial numbers" }}</h3>
      <p class="mb-2 text-xs" :class="matches ? 'text-green-600' : 'text-amber-600'">
        {{ count }} / {{ required }} entered — one serial per line
      </p>
      <textarea
        v-model="text"
        rows="8"
        class="form-input font-mono text-sm"
        placeholder="One serial number per line"
      ></textarea>
      <div class="mt-3 flex justify-end gap-2">
        <button type="button" class="btn-secondary" @click="emit('close')">Cancel</button>
        <button type="button" class="btn-primary" @click="done">Done</button>
      </div>
    </div>
  </div>
</template>
