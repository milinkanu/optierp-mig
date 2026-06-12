import type { Config } from "tailwindcss";

// Brand colors come from CSS variables set at runtime from /brand/config.json
// (Section 5.1 — zero hardcoded branding).
export default {
  content: ["./index.html", "./src/**/*.{vue,ts}"],
  theme: {
    extend: {
      colors: {
        primary: "rgb(var(--brand-primary) / <alpha-value>)",
        secondary: "rgb(var(--brand-secondary) / <alpha-value>)",
      },
    },
  },
  plugins: [],
} satisfies Config;
