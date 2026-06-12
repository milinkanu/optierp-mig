<script setup lang="ts">
import { useRoute, useRouter } from "vue-router";
import { brand } from "@/brand";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

// Module 02+ add their entries here as they are migrated
const navigation = [
  { name: "Dashboard", route: "dashboard", icon: "▦" },
  { name: "Companies", route: "companies", icon: "🏢" },
  { name: "Users", route: "users", icon: "👤" },
  { name: "Roles", route: "roles", icon: "🛡" },
  { name: "Settings", route: "settings", icon: "⚙" },
];

async function logout(): Promise<void> {
  await auth.logout();
  void router.push({ name: "login" });
}
</script>

<template>
  <div class="flex min-h-screen">
    <aside class="flex w-60 flex-col border-r border-gray-200 bg-white">
      <div class="flex items-center gap-3 border-b border-gray-200 px-4 py-4">
        <img :src="brand.logo_url" :alt="brand.product_name" class="h-8 w-8" />
        <div>
          <div class="text-sm font-semibold text-gray-900">{{ brand.product_name }}</div>
          <div class="text-xs text-gray-500">{{ brand.tagline }}</div>
        </div>
      </div>
      <nav class="flex-1 space-y-1 p-3">
        <RouterLink
          v-for="item in navigation"
          :key="item.route"
          :to="{ name: item.route }"
          class="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium"
          :class="
            route.name === item.route
              ? 'bg-primary/10 text-primary'
              : 'text-gray-600 hover:bg-gray-100'
          "
        >
          <span aria-hidden="true">{{ item.icon }}</span>
          {{ item.name }}
        </RouterLink>
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
      <RouterView />
    </main>
  </div>
</template>
