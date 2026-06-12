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
      // Module 02+ routes (accounts/, stock/, ...) register here per module
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
