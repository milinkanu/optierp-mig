// Lazy-loaded routes per module with an auth guard.

import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const routes: RouteRecordRaw[] = [
  {
    path: "/login",
    name: "login",
    component: () => import("@/views/auth/LoginView.vue"),
    meta: { public: true },
  },
  {
    path: "/",
    component: () => import("@/layouts/AppShell.vue"),
    children: [
      { path: "", name: "dashboard", component: () => import("@/views/dashboard/DashboardView.vue") },
      // Module 01 — Core / Setup
      {
        path: "companies",
        name: "companies",
        component: () => import("@/views/core/CompanyListView.vue"),
      },
      {
        path: "companies/new",
        name: "company-new",
        component: () => import("@/views/core/CompanyFormView.vue"),
      },
      {
        path: "companies/:id",
        name: "company-detail",
        component: () => import("@/views/core/CompanyFormView.vue"),
        props: true,
      },
      { path: "users", name: "users", component: () => import("@/views/core/UserListView.vue") },
      { path: "users/new", name: "user-new", component: () => import("@/views/core/UserFormView.vue") },
      { path: "roles", name: "roles", component: () => import("@/views/core/RoleListView.vue") },
      {
        path: "settings",
        name: "settings",
        component: () => import("@/views/core/SettingsView.vue"),
      },
      // Module 02 — Accounts
      {
        path: "sales-invoices",
        name: "sales-invoices",
        component: () => import("@/views/accounts/InvoiceListView.vue"),
        props: { kind: "sales" },
      },
      {
        path: "sales-invoices/new",
        name: "sales-invoice-new",
        component: () => import("@/views/accounts/InvoiceFormView.vue"),
        props: { kind: "sales" },
      },
      {
        path: "sales-invoices/:id",
        name: "sales-invoice-detail",
        component: () => import("@/views/accounts/InvoiceFormView.vue"),
        props: (route) => ({ kind: "sales", id: route.params.id as string }),
      },
      {
        path: "purchase-invoices",
        name: "purchase-invoices",
        component: () => import("@/views/accounts/InvoiceListView.vue"),
        props: { kind: "purchase" },
      },
      {
        path: "purchase-invoices/new",
        name: "purchase-invoice-new",
        component: () => import("@/views/accounts/InvoiceFormView.vue"),
        props: { kind: "purchase" },
      },
      {
        path: "purchase-invoices/:id",
        name: "purchase-invoice-detail",
        component: () => import("@/views/accounts/InvoiceFormView.vue"),
        props: (route) => ({ kind: "purchase", id: route.params.id as string }),
      },
      {
        path: "journal-entries",
        name: "journal-entries",
        component: () => import("@/views/accounts/JournalEntryView.vue"),
      },
      {
        path: "payment-entries",
        name: "payment-entries",
        component: () => import("@/views/accounts/PaymentEntryView.vue"),
      },
      {
        path: "payment-reconciliation",
        name: "payment-reconciliation",
        component: () => import("@/views/accounts/PaymentReconciliationView.vue"),
      },
      {
        path: "budgets",
        name: "budgets",
        component: () => import("@/views/accounts/BudgetView.vue"),
      },
      {
        path: "reports",
        name: "reports",
        component: () => import("@/views/accounts/ReportsView.vue"),
      },
      // Module 03+ routes (stock/, buying/, ...) register here per module
    ],
  },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (!auth.initialized) {
    await auth.restoreSession();
  }
  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  if (to.name === "login" && auth.isAuthenticated) {
    return { name: "dashboard" };
  }
});
