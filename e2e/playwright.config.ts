import { defineConfig, devices } from "@playwright/test";

// Config for the test runner + `playwright codegen`. The capture harness
// (capture.mjs) runs standalone and does not use this file.
export default defineConfig({
  testDir: "./tests",
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:5173",
    viewport: { width: 1600, height: 1000 },
    screenshot: "only-on-failure",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
