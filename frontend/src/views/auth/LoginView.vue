<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { brand } from "@/brand";
import { useAuthStore } from "@/stores/auth";
import type { ErrorEnvelope } from "@/types/core";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();

const email = ref("");
const password = ref("");
const loading = ref(false);
const error = ref<string | null>(null);

async function submit(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    await auth.login(email.value, password.value);
    const redirect = (route.query.redirect as string) ?? "/";
    void router.push(redirect);
  } catch (e) {
    error.value = (e as ErrorEnvelope).detail ?? "Login failed";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-gray-50 px-4">
    <div class="w-full max-w-sm">
      <div class="mb-8 text-center">
        <img :src="brand.logo_url" :alt="brand.product_name" class="mx-auto h-14 w-14" />
        <h1 class="mt-4 text-xl font-semibold text-gray-900">{{ brand.product_name }}</h1>
        <p class="text-sm text-gray-500">{{ brand.tagline }}</p>
      </div>
      <form class="space-y-4 rounded-lg border border-gray-200 bg-white p-6 shadow-sm" @submit.prevent="submit">
        <div>
          <label for="email" class="form-label">Email</label>
          <input id="email" v-model="email" type="email" required autocomplete="email" class="form-input" />
        </div>
        <div>
          <label for="password" class="form-label">Password</label>
          <input
            id="password"
            v-model="password"
            type="password"
            required
            autocomplete="current-password"
            class="form-input"
          />
        </div>
        <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
        <button type="submit" class="btn-primary w-full" :disabled="loading">
          {{ loading ? "Signing in…" : "Sign in" }}
        </button>
      </form>
      <p class="mt-4 text-center text-xs text-gray-400">
        Need help? <a :href="`mailto:${brand.support_email}`" class="text-primary">{{ brand.support_email }}</a>
      </p>
    </div>
  </div>
</template>
