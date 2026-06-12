// Client-side role helpers. The server is the source of truth (403s);
// these only drive UI affordances like hiding buttons.

import { computed } from "vue";
import { useAuthStore } from "@/stores/auth";

export function usePermissions() {
  const auth = useAuthStore();

  const roles = computed(() => auth.roles);
  const isSystemManager = computed(() => auth.isSystemManager);

  function hasRole(...required: string[]): boolean {
    if (auth.isSystemManager) return true;
    return required.some((r) => auth.roles.includes(r));
  }

  return { roles, isSystemManager, hasRole };
}
