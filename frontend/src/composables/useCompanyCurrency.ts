// Active company's base currency for formatting company-currency amounts
// (dashboard cards, payments, journal entries, budgets, reconciliation).

import { computed, type ComputedRef } from "vue";
import { useAuthStore } from "@/stores/auth";
import { useCoreStore } from "@/stores/core";

export function useCompanyCurrency(): ComputedRef<string> {
  const auth = useAuthStore();
  const core = useCoreStore();
  if (!core.companies.length) {
    void core.fetchCompanies();
  }
  return computed(() => {
    const company = core.companies.find((c) => c.id === auth.companyId);
    return company?.default_currency ?? "INR";
  });
}
