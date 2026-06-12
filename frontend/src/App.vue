<script setup lang="ts">
import { onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const router = useRouter();
const auth = useAuthStore();

function onAuthExpired(): void {
  auth.$reset();
  auth.initialized = true;
  void router.push({ name: "login" });
}

onMounted(() => window.addEventListener("auth:expired", onAuthExpired));
onUnmounted(() => window.removeEventListener("auth:expired", onAuthExpired));
</script>

<template>
  <RouterView />
</template>
