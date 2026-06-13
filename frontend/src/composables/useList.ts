// Generic paginated list with filters/sort for any module endpoint.

import { ref, type Ref } from "vue";
import { api } from "@/api/client";
import type { ErrorEnvelope, ListResponse } from "@/types/core";

export function useList<T>(endpoint: string | (() => string)) {
  const items: Ref<T[]> = ref([]);
  const total = ref(0);
  const page = ref(1);
  const pageSize = ref(20);
  const loading = ref(false);
  const error = ref<ErrorEnvelope | null>(null);
  const filters = ref<Record<string, string | number | boolean | undefined>>({});

  const resolveEndpoint = (): string => (typeof endpoint === "function" ? endpoint() : endpoint);

  async function fetchList(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const resp = await api.get<ListResponse<T>>(resolveEndpoint(), {
        params: { page: page.value, page_size: pageSize.value, ...filters.value },
      });
      items.value = resp.data.items;
      total.value = resp.data.total;
    } catch (e) {
      error.value = e as ErrorEnvelope;
    } finally {
      loading.value = false;
    }
  }

  async function goToPage(p: number): Promise<void> {
    page.value = p;
    await fetchList();
  }

  /** Reset paging/filters (e.g. when the underlying endpoint switches). */
  async function reset(): Promise<void> {
    page.value = 1;
    filters.value = {};
    await fetchList();
  }

  return { items, total, page, pageSize, loading, error, filters, fetchList, goToPage, reset };
}
