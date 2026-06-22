<script setup lang="ts">
// Opens the document preview modal. `path` is the print endpoint base (without the
// ?format query), e.g. "/sales-invoices/<id>/pdf" or "/print/Sales Invoice/<id>".
import { ref } from "vue";
import PrintPreviewModal from "@/components/shared/PrintPreviewModal.vue";

defineProps<{ path: string; label?: string; title?: string }>();
const open = ref(false);
</script>

<template>
  <button type="button" class="btn-secondary" @click="open = true">{{ label || "Print / PDF" }}</button>
  <PrintPreviewModal v-if="open" :path="path" :title="title" @close="open = false" />
</template>
