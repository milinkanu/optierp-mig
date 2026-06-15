<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { brand } from "@/brand";
import { WORKSPACES, type WsNavGroup } from "@/config/workspaces";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

// Global sidebar (shown outside any module — e.g. Setup pages).
const GLOBAL_NAV: WsNavGroup[] = [
  {
    items: [
      { label: "Home", to: "/", icon: "⌂" },
      { label: "Selling", to: "/selling", icon: "🧭" },
      { label: "Buying", to: "/buying", icon: "🛍" },
      { label: "Stock", to: "/stock", icon: "📦" },
      { label: "Accounting", to: "/accounting", icon: "📊" },
    ],
  },
  {
    title: "Setup",
    items: [
      { label: "Companies", to: "/companies", icon: "🏢" },
      { label: "Users", to: "/users", icon: "👤" },
      { label: "Roles", to: "/roles", icon: "🛡" },
      { label: "Settings", to: "/settings", icon: "⚙" },
    ],
  },
];

// Map every module's routes -> module key (from the workspace configs), so we can
// tell which module the current page belongs to and keep that sidebar showing.
const ROUTE_MODULE: Record<string, string> = {};
for (const [key, cfg] of Object.entries(WORKSPACES)) {
  ROUTE_MODULE[`/${key}`] = key;
  for (const group of cfg.sidebar) {
    for (const item of group.items) {
      if (item.to !== "/" && !(item.to in ROUTE_MODULE)) ROUTE_MODULE[item.to] = key;
    }
  }
}
const MODULE_PATHS = Object.keys(ROUTE_MODULE).sort((a, b) => b.length - a.length);

function moduleForPath(path: string): string | null {
  if (path.startsWith("/m/")) return "selling"; // engine masters are Selling-group
  for (const p of MODULE_PATHS) {
    if (path === p || path.startsWith(`${p}/`)) return ROUTE_MODULE[p];
  }
  return null;
}

const isHome = computed(() => route.name === "dashboard"); // launcher: full-page, no sidebar
const activeModule = computed(() => moduleForPath(route.path));
const sidebarGroups = computed<WsNavGroup[]>(() =>
  activeModule.value ? WORKSPACES[activeModule.value].sidebar : GLOBAL_NAV,
);
const headerTitle = computed(() =>
  activeModule.value ? WORKSPACES[activeModule.value].title : brand.value.product_name,
);
const headerSubtitle = computed(() =>
  activeModule.value ? brand.value.product_name : brand.value.tagline,
);

function isActive(to: string): boolean {
  if (to === "/") return route.path === "/";
  return route.path === to || route.path.startsWith(`${to}/`);
}

async function logout(): Promise<void> {
  await auth.logout();
  void router.push({ name: "login" });
}
</script>

<template>
  <div class="flex min-h-screen">
    <aside v-if="!isHome" class="flex w-60 flex-col border-r border-gray-200 bg-white">
      <div class="flex items-center gap-3 border-b border-gray-200 px-4 py-4">
        <img :src="brand.logo_url" :alt="brand.product_name" class="h-8 w-8" />
        <div>
          <div class="text-sm font-semibold text-gray-900">{{ headerTitle }}</div>
          <div class="text-xs text-gray-500">{{ headerSubtitle }}</div>
        </div>
      </div>
      <nav class="flex-1 overflow-y-auto p-3">
        <div v-for="(group, gi) in sidebarGroups" :key="gi" class="mb-2">
          <div
            v-if="group.title"
            class="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-gray-400"
          >
            {{ group.title }}
          </div>
          <RouterLink
            v-for="item in group.items"
            :key="item.to"
            :to="item.to"
            class="flex items-center gap-3 rounded-md px-3 py-1.5 text-sm font-medium"
            :class="
              isActive(item.to)
                ? 'bg-primary/10 text-primary'
                : 'text-gray-600 hover:bg-gray-100'
            "
          >
            <span v-if="item.icon" aria-hidden="true">{{ item.icon }}</span>
            {{ item.label }}
          </RouterLink>
        </div>
      </nav>
      <div class="border-t border-gray-200 p-4">
        <div class="text-sm font-medium text-gray-900">{{ auth.fullName }}</div>
        <div class="truncate text-xs text-gray-500">{{ auth.email }}</div>
        <button class="mt-2 text-xs font-medium text-primary hover:underline" @click="logout">
          Sign out
        </button>
      </div>
    </aside>
    <main class="flex-1 overflow-y-auto p-6">
      <!-- keyed by fullPath: reusing a component instance across e.g.
           /quotations/:id -> /sales-orders/new would keep stale state -->
      <RouterView :key="route.fullPath" />
    </main>
  </div>
</template>
