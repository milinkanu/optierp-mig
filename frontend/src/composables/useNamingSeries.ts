// Naming series preview (e.g. show "SINV-2026-00012" next to the pattern field).

import { ref } from "vue";
import { api } from "@/api/client";
import type { ErrorEnvelope } from "@/types/core";

interface PreviewResponse {
  pattern: string;
  next_name: string;
}

export function useNamingSeries() {
  const nextName = ref<string | null>(null);
  const loading = ref(false);
  const error = ref<ErrorEnvelope | null>(null);

  async function preview(pattern: string): Promise<void> {
    loading.value = true;
    error.value = null;
    nextName.value = null;
    try {
      const resp = await api.post<PreviewResponse>("/naming-series/preview", { pattern });
      nextName.value = resp.data.next_name;
    } catch (e) {
      error.value = e as ErrorEnvelope;
    } finally {
      loading.value = false;
    }
  }

  return { nextName, loading, error, preview };
}
