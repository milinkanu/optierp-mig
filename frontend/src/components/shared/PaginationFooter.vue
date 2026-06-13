<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ page: number; pageSize: number; total: number }>();
const emit = defineEmits<{ goTo: [page: number] }>();

const lastPage = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)));
const from = computed(() => (props.total === 0 ? 0 : (props.page - 1) * props.pageSize + 1));
const to = computed(() => Math.min(props.page * props.pageSize, props.total));
</script>

<template>
  <div v-if="total > pageSize" class="mt-3 flex items-center justify-between text-sm text-gray-600">
    <span>{{ from }}–{{ to }} of {{ total }}</span>
    <div class="flex items-center gap-2">
      <button class="btn-secondary" :disabled="page <= 1" @click="emit('goTo', page - 1)">
        ← Prev
      </button>
      <span class="px-1">Page {{ page }} / {{ lastPage }}</span>
      <button class="btn-secondary" :disabled="page >= lastPage" @click="emit('goTo', page + 1)">
        Next →
      </button>
    </div>
  </div>
</template>
