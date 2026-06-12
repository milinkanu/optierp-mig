<script setup lang="ts">
// Docstatus / boolean status pill matching ERPNext semantics.
const props = defineProps<{ status: string | number | boolean }>();

function tone(): string {
  const s = props.status;
  if (s === 1 || s === true || s === "Submitted" || s === "Active" || s === "Enabled") {
    return "bg-green-100 text-green-800";
  }
  if (s === 2 || s === "Cancelled" || s === "Disabled" || s === false) {
    return "bg-red-100 text-red-700";
  }
  return "bg-gray-100 text-gray-700"; // 0 / Draft / neutral
}

function label(): string {
  const s = props.status;
  if (typeof s === "number") return ["Draft", "Submitted", "Cancelled"][s] ?? String(s);
  if (typeof s === "boolean") return s ? "Active" : "Disabled";
  return s;
}
</script>

<template>
  <span class="inline-flex rounded-full px-2 py-0.5 text-xs font-medium" :class="tone()">
    {{ label() }}
  </span>
</template>
