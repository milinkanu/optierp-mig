<script setup lang="ts">
import { onMounted } from "vue";
import { brand } from "@/brand";
import { useAuthStore } from "@/stores/auth";
import { useCoreStore } from "@/stores/core";

const auth = useAuthStore();
const core = useCoreStore();

onMounted(() => {
  void core.fetchCompanies();
});
</script>

<template>
  <div>
    <h1 class="text-2xl font-semibold text-gray-900">Welcome, {{ auth.fullName }}</h1>
    <p class="mt-1 text-sm text-gray-500">{{ brand.product_name }} — Phase 1: Core &amp; Setup</p>

    <div class="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
      <div class="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <div class="text-sm text-gray-500">Companies</div>
        <div class="mt-1 text-3xl font-semibold text-gray-900">{{ core.companiesTotal }}</div>
        <RouterLink :to="{ name: 'companies' }" class="mt-2 inline-block text-sm text-primary hover:underline">
          Manage companies →
        </RouterLink>
      </div>
      <div class="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <div class="text-sm text-gray-500">Your roles</div>
        <div class="mt-2 flex flex-wrap gap-1">
          <span
            v-for="role in auth.roles"
            :key="role"
            class="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
          >
            {{ role }}
          </span>
          <span v-if="auth.roles.length === 0" class="text-sm text-gray-400">No roles assigned</span>
        </div>
      </div>
      <div class="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <div class="text-sm text-gray-500">Coming next</div>
        <p class="mt-1 text-sm text-gray-700">
          Accounts (GL, invoices, payments), Stock, Buying &amp; Selling modules.
        </p>
      </div>
    </div>
  </div>
</template>
