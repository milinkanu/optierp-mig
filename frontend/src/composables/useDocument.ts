// Generic CRUD for a single document of any type (mirrors frappe.get_doc usage).

import { ref, type Ref } from "vue";
import { api } from "@/api/client";
import type { ErrorEnvelope } from "@/types/core";

export function useDocument<T extends { id: string }>(endpoint: string) {
  const doc: Ref<T | null> = ref(null);
  const loading = ref(false);
  const saving = ref(false);
  const error = ref<ErrorEnvelope | null>(null);

  async function load(id: string): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      doc.value = (await api.get<T>(`${endpoint}/${id}`)).data;
    } catch (e) {
      error.value = e as ErrorEnvelope;
    } finally {
      loading.value = false;
    }
  }

  async function create(payload: Record<string, unknown>): Promise<T | null> {
    saving.value = true;
    error.value = null;
    try {
      doc.value = (await api.post<T>(endpoint, payload)).data;
      return doc.value;
    } catch (e) {
      error.value = e as ErrorEnvelope;
      return null;
    } finally {
      saving.value = false;
    }
  }

  async function update(id: string, payload: Record<string, unknown>): Promise<T | null> {
    saving.value = true;
    error.value = null;
    try {
      doc.value = (await api.patch<T>(`${endpoint}/${id}`, payload)).data;
      return doc.value;
    } catch (e) {
      error.value = e as ErrorEnvelope;
      return null;
    } finally {
      saving.value = false;
    }
  }

  return { doc, loading, saving, error, load, create, update };
}
