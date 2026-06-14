<script setup lang="ts">
// Generic ERPNext-style module workspace: its own module sidebar + content
// (trend chart + number cards + grouped "Reports & Masters" grid), driven by a
// WorkspaceConfig. Selling and Buying both render this page. Self-contained
// full-page layout (a top-level route, not under AppShell).

import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { api } from "@/api/client";
import { brand } from "@/brand";
import TrendChart from "@/components/shared/TrendChart.vue";
import { WORKSPACES } from "@/config/workspaces";
import { useAuthStore } from "@/stores/auth";
import { formatCurrency } from "@/utils/format";

const props = defineProps<{ moduleKey: string }>();

interface StatCard {
  label: string;
  value: number;
  format: "int" | "currency";
}
interface Stats {
  currency: string;
  chart_title: string;
  cards: StatCard[];
  trend: { label: string; value: number }[];
}

const route = useRoute();
const auth = useAuthStore();

const config = computed(() => WORKSPACES[props.moduleKey]);
const stats = ref<Stats | null>(null);
const loading = ref(true);

async function loadStats(): Promise<void> {
  loading.value = true;
  stats.value = null;
  try {
    if (config.value) stats.value = (await api.get<Stats>(config.value.statsEndpoint)).data;
  } catch {
    stats.value = null;
  } finally {
    loading.value = false;
  }
}

onMounted(loadStats);
watch(() => props.moduleKey, loadStats);

function isActive(to: string): boolean {
  return route.path === to;
}
function display(card: StatCard, currency: string): string {
  return card.format === "currency" ? formatCurrency(card.value, currency) : String(card.value);
}
</script>

<template>
  <div v-if="config" class="flex min-h-screen bg-gray-50">
    <!-- module sidebar -->
    <aside class="flex w-60 flex-shrink-0 flex-col border-r border-gray-200 bg-white">
      <div class="flex items-center gap-3 border-b border-gray-200 px-4 py-4">
        <img :src="brand.logo_url" :alt="brand.product_name" class="h-8 w-8" />
        <div>
          <div class="text-sm font-semibold text-gray-900">{{ config.title }}</div>
          <div class="text-xs text-gray-500">{{ brand.product_name }}</div>
        </div>
      </div>
      <nav class="flex-1 overflow-y-auto p-3">
        <div v-for="(group, gi) in config.sidebar" :key="gi" class="mb-2">
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
            :class="isActive(item.to) ? 'bg-primary/10 text-primary' : 'text-gray-600 hover:bg-gray-100'"
          >
            <span v-if="item.icon" aria-hidden="true">{{ item.icon }}</span>
            {{ item.label }}
          </RouterLink>
        </div>
      </nav>
      <div class="border-t border-gray-200 p-4">
        <div class="truncate text-xs text-gray-500">{{ auth.email }}</div>
        <RouterLink to="/" class="mt-1 inline-block text-xs font-medium text-primary hover:underline">
          ← Back to app
        </RouterLink>
      </div>
    </aside>

    <!-- content -->
    <main class="flex-1 overflow-y-auto p-6">
      <h1 class="mb-4 text-xl font-semibold text-gray-900">{{ config.title }}</h1>

      <!-- trend chart -->
      <div class="mb-4 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <h2 class="mb-3 text-sm font-semibold text-gray-700">
          {{ stats?.chart_title ?? "Trends" }}
        </h2>
        <p v-if="loading" class="py-12 text-center text-sm text-gray-400">Loading…</p>
        <TrendChart v-else-if="stats" :points="stats.trend" :height="220" />
        <p v-else class="py-12 text-center text-sm text-gray-400">No data available</p>
      </div>

      <!-- number cards -->
      <div class="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div
          v-for="card in stats?.cards ?? []"
          :key="card.label"
          class="rounded-lg border border-gray-200 bg-white p-5 shadow-sm"
        >
          <div class="text-sm text-gray-500">{{ card.label }}</div>
          <div class="mt-1 text-3xl font-semibold text-gray-900">
            {{ display(card, stats?.currency ?? "INR") }}
          </div>
        </div>
      </div>

      <!-- reports & masters -->
      <h2 class="mb-3 text-base font-semibold text-gray-500">Reports &amp; Masters</h2>
      <div class="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
        <div
          v-for="card in config.cards"
          :key="card.title"
          class="rounded-lg border border-gray-200 bg-white p-5 shadow-sm"
        >
          <h3 class="mb-3 text-sm font-semibold text-gray-800">{{ card.title }}</h3>
          <ul class="space-y-2">
            <li v-for="link in card.links" :key="link.label" class="text-sm">
              <RouterLink v-if="link.to" :to="link.to" class="text-primary hover:underline">
                {{ link.label }} ↗
              </RouterLink>
              <span v-else class="text-gray-400" title="Coming soon">
                {{ link.label }}
                <span class="ml-1 rounded bg-gray-100 px-1 text-[10px] uppercase">soon</span>
              </span>
            </li>
          </ul>
        </div>
      </div>
    </main>
  </div>
</template>
