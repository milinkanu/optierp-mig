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
      // Module 03 — Stock
      { path: "items", name: "items", component: () => import("@/views/stock/ItemsView.vue") },
      {
        path: "warehouses",
        name: "warehouses",
        component: () => import("@/views/stock/WarehousesView.vue"),
      },
      {
        path: "stock-entries",
        name: "stock-entries",
        component: () => import("@/views/stock/StockEntryView.vue"),
      },
      {
        path: "material-requests",
        name: "material-requests",
        component: () => import("@/views/stock/MaterialRequestView.vue"),
      },
      {
        path: "stock-balance",
        name: "stock-balance",
        component: () => import("@/views/stock/StockBalanceView.vue"),
      },
      {
        path: "purchase-receipts",
        name: "purchase-receipts",
        component: () => import("@/views/trade/FulfilmentView.vue"),
        props: { kind: "purchase-receipt" },
      },
      {
        path: "purchase-receipts/:id",
        name: "purchase-receipt-detail",
        component: () => import("@/views/trade/FulfilmentView.vue"),
        props: (route) => ({ kind: "purchase-receipt", id: route.params.id as string }),
      },
      {
        path: "delivery-notes",
        name: "delivery-notes",
        component: () => import("@/views/trade/FulfilmentView.vue"),
        props: { kind: "delivery-note" },
      },
      {
        path: "delivery-notes/:id",
        name: "delivery-note-detail",
        component: () => import("@/views/trade/FulfilmentView.vue"),
        props: (route) => ({ kind: "delivery-note", id: route.params.id as string }),
      },
      // Module 04 — Buying
      {
        path: "purchase-orders",
        name: "purchase-orders",
        component: () => import("@/views/trade/OrderListView.vue"),
        props: { kind: "purchase-order" },
      },
      {
        path: "purchase-orders/new",
        name: "purchase-order-new",
        component: () => import("@/views/trade/OrderFormView.vue"),
        props: { kind: "purchase-order" },
      },
      {
        path: "purchase-orders/:id",
        name: "purchase-order-detail",
        component: () => import("@/views/trade/OrderFormView.vue"),
        props: (route) => ({ kind: "purchase-order", id: route.params.id as string }),
      },
      { path: "sourcing", name: "sourcing", component: () => import("@/views/buying/RfqView.vue") },
      // Module 05 — Selling
      {
        path: "quotations",
        name: "quotations",
        component: () => import("@/views/trade/OrderListView.vue"),
        props: { kind: "quotation" },
      },
      {
        path: "quotations/new",
        name: "quotation-new",
        component: () => import("@/views/trade/OrderFormView.vue"),
        props: { kind: "quotation" },
      },
      {
        path: "quotations/:id",
        name: "quotation-detail",
        component: () => import("@/views/trade/OrderFormView.vue"),
        props: (route) => ({ kind: "quotation", id: route.params.id as string }),
      },
      {
        path: "sales-orders",
        name: "sales-orders",
        component: () => import("@/views/trade/OrderListView.vue"),
        props: { kind: "sales-order" },
      },
      {
        path: "sales-orders/new",
        name: "sales-order-new",
        component: () => import("@/views/trade/OrderFormView.vue"),
        props: { kind: "sales-order" },
      },
      {
        path: "sales-orders/:id",
        name: "sales-order-detail",
        component: () => import("@/views/trade/OrderFormView.vue"),
        props: (route) => ({ kind: "sales-order", id: route.params.id as string }),
      },
      // Metadata engine ("the machine") — generic list/form for any registered DocType.
      // Adding a master needs NO new route here; it is reached via /m/<slug>.
      {
        path: "m/:doctype",
        name: "generic-list",
        component: () => import("@/views/generic/GenericListView.vue"),
        props: true,
      },
      {
        path: "m/:doctype/:id",
        name: "generic-form",
        component: () => import("@/views/generic/GenericFormView.vue"),
        props: true,
      },
      // Module 06+ routes register here per module
    ],
  },
  // ERPNext-style Selling workspace — a self-contained full page (own sidebar),
  // so it is a top-level route, not wrapped by the AppShell layout.
  {
    path: "/selling",
    name: "selling-workspace",
    component: () => import("@/views/selling/SellingWorkspace.vue"),
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
