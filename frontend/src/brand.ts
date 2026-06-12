// White-label bootstrap (Section 5.1): all branding comes from
// /brand/config.json — product name, colors, logo. No hardcoded brand
// strings anywhere else in the app.

import type { BrandConfig } from "@/types/core";
import { ref } from "vue";

export const brand = ref<BrandConfig>({
  product_name: "",
  tagline: "",
  logo_url: "/brand/logo.svg",
  favicon_url: "/brand/favicon.svg",
  primary_color: "#4F46E5",
  secondary_color: "#7C3AED",
  support_email: "",
  docs_url: "",
});

function hexToRgbTriplet(hex: string): string {
  const value = hex.replace("#", "");
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  return `${r} ${g} ${b}`;
}

export async function loadBrand(): Promise<void> {
  const resp = await fetch("/brand/config.json");
  brand.value = (await resp.json()) as BrandConfig;

  document.title = brand.value.product_name;
  const root = document.documentElement;
  root.style.setProperty("--brand-primary", hexToRgbTriplet(brand.value.primary_color));
  root.style.setProperty("--brand-secondary", hexToRgbTriplet(brand.value.secondary_color));

  let favicon = document.querySelector<HTMLLinkElement>("link[rel='icon']");
  if (!favicon) {
    favicon = document.createElement("link");
    favicon.rel = "icon";
    document.head.appendChild(favicon);
  }
  favicon.href = brand.value.favicon_url;
}
