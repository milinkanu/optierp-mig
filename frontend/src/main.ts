import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { router } from "./router";
import { loadBrand } from "./brand";
import "./style.css";

async function bootstrap(): Promise<void> {
  await loadBrand(); // branding before first paint — no flash of unbranded UI
  const app = createApp(App);
  app.use(createPinia());
  app.use(router);
  app.mount("#app");
}

void bootstrap();
