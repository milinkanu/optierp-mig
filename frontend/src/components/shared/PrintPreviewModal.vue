<script setup lang="ts">
// In-app document preview. Fetches the themed HTML with auth and renders it in a
// sandboxed iframe (srcdoc — a raw iframe navigation can't carry the bearer token).
// Download PDF reuses the binary helper; Print drives the iframe's own print dialog.
import { onMounted, ref } from "vue";
import { fetchPrintHtml, openPdf } from "@/api/client";
import type { ErrorEnvelope } from "@/types/core";

const props = defineProps<{ path: string; title?: string }>();
const emit = defineEmits<{ close: [] }>();

const html = ref("");
const loading = ref(true);
const downloading = ref(false);
const error = ref<ErrorEnvelope | null>(null);
const iframeEl = ref<HTMLIFrameElement | null>(null);

onMounted(async () => {
  try {
    html.value = await fetchPrintHtml(`${props.path}?format=html`);
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    loading.value = false;
  }
});

async function download(): Promise<void> {
  downloading.value = true;
  error.value = null;
  try {
    await openPdf(`${props.path}?format=pdf`);
  } catch (e) {
    error.value = e as ErrorEnvelope;
  } finally {
    downloading.value = false;
  }
}

function printDoc(): void {
  iframeEl.value?.contentWindow?.print();
}
</script>

<template>
  <div class="fixed inset-0 z-50 flex flex-col bg-black/40 p-4" @click.self="emit('close')">
    <div class="mx-auto flex h-full w-full max-w-4xl flex-col overflow-hidden rounded-lg bg-white shadow-xl">
      <div class="flex items-center justify-between border-b border-gray-200 px-5 py-3">
        <h3 class="text-sm font-semibold text-gray-900">{{ title || "Document preview" }}</h3>
        <div class="flex items-center gap-2">
          <button type="button" class="btn-secondary" :disabled="loading || !!error" @click="printDoc">
            Print
          </button>
          <button
            type="button"
            class="btn-primary"
            :disabled="loading || downloading || !!error"
            @click="download"
          >
            {{ downloading ? "Preparing…" : "Download PDF" }}
          </button>
          <button type="button" class="btn-secondary" @click="emit('close')">Close</button>
        </div>
      </div>
      <div class="relative flex-1 overflow-hidden bg-gray-100">
        <div v-if="loading" class="absolute inset-0 flex items-center justify-center text-sm text-gray-500">
          Loading preview…
        </div>
        <p
          v-else-if="error"
          class="absolute inset-0 flex items-center justify-center px-6 text-center text-sm text-red-600"
        >
          {{ error.detail }}
        </p>
        <iframe
          v-show="!loading && !error"
          ref="iframeEl"
          :srcdoc="html"
          class="h-full w-full border-0 bg-white"
          sandbox="allow-same-origin allow-modals"
          title="Document preview"
        ></iframe>
      </div>
    </div>
  </div>
</template>
