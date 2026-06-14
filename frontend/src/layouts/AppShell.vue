<script setup lang="ts">
import { useRoute, useRouter } from "vue-router";
import { brand } from "@/brand";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

interface NavItem {
  name: string;
  route: string;
  icon: string;
  params?: Record<string, string>;
}
interface NavGroup {
  section: string;
  items: NavItem[];
}

// Grouped per module; Module 06+ add their sections here as they are migrated.
// Items with `params` target the metadata-engine generic views (route "generic-list").
const navigation: NavGroup[] = [
  {
    section: "",
    items: [{ name: "Dashboard", route: "dashboard", icon: "▦" }],
  },
  {
    section: "Selling",
    items: [
      { name: "Quotations", route: "quotations", icon: "📝" },
      { name: "Sales Orders", route: "sales-orders", icon: "🛒" },
      { name: "Delivery Notes", route: "delivery-notes", icon: "🚚" },
      { name: "Sales Invoices", route: "sales-invoices", icon: "🧾" },
      { name: "Campaigns", route: "generic-list", icon: "📣", params: { doctype: "campaign" } },
    ],
  },
  {
    section: "Buying",
    items: [
      { name: "Material Requests", route: "material-requests", icon: "📋" },
      { name: "Sourcing (RFQ)", route: "sourcing", icon: "📨" },
      { name: "Purchase Orders", route: "purchase-orders", icon: "🛍" },
      { name: "Purchase Receipts", route: "purchase-receipts", icon: "📦" },
      { name: "Purchase Invoices", route: "purchase-invoices", icon: "📥" },
    ],
  },
  {
    section: "Stock",
    items: [
      { name: "Items", route: "items", icon: "🏷" },
      { name: "Warehouses", route: "warehouses", icon: "🏬" },
      { name: "Stock Entries", route: "stock-entries", icon: "↔" },
      { name: "Stock Balance", route: "stock-balance", icon: "📈" },
    ],
  },
  {
    section: "Accounting",
    items: [
      { name: "Journal Entries", route: "journal-entries", icon: "📒" },
      { name: "Payments", route: "payment-entries", icon: "💸" },
      { name: "Reconciliation", route: "payment-reconciliation", icon: "🔗" },
      { name: "Budgets", route: "budgets", icon: "🎯" },
      { name: "Reports", route: "reports", icon: "📊" },
    ],
  },
  {
    section: "Setup",
    items: [
      { name: "Companies", route: "companies", icon: "🏢" },
      { name: "Users", route: "users", icon: "👤" },
      { name: "Roles", route: "roles", icon: "🛡" },
      { name: "Settings", route: "settings", icon: "⚙" },
    ],
  },
];

function linkTo(item: NavItem) {
  return item.params ? { name: item.route, params: item.params } : { name: item.route };
}
function isActive(item: NavItem): boolean {
  if (route.name !== item.route) return false;
  if (item.params?.doctype) return route.params.doctype === item.params.doctype;
  return true;
}

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
      <nav class="flex-1 overflow-y-auto p-3">
        <div v-for="group in navigation" :key="group.section" class="mb-2">
          <div v-if="group.section"
               class="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-gray-400">
            {{ group.section }}
          </div>
          <RouterLink
            v-for="item in group.items"
            :key="item.name"
            :to="linkTo(item)"
            class="flex items-center gap-3 rounded-md px-3 py-1.5 text-sm font-medium"
            :class="
              isActive(item)
                ? 'bg-primary/10 text-primary'
                : 'text-gray-600 hover:bg-gray-100'
            "
          >
            <span aria-hidden="true">{{ item.icon }}</span>
            {{ item.name }}
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
