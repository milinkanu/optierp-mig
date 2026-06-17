import { test, expect } from "@playwright/test";

// Hands-on example spec. Run with `npm test` (from e2e/) while the dev app is up.
// Use `npm run codegen` to record new flows by clicking through the app.

const EMAIL = process.env.ADMIN_EMAIL ?? "admin@example.com";
const PASSWORD = process.env.ADMIN_PASSWORD ?? "ChangeMe!123";

test.beforeEach(async ({ page }) => {
  await page.goto("/login");
  await page.fill("#email", EMAIL);
  await page.fill("#password", PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
});

test("new quotation form shows the ERPNext-style items grid + Get Items From", async ({ page }) => {
  await page.goto("/quotations/new");
  await expect(page.getByText("New Quotation")).toBeVisible();
  await expect(page.getByRole("button", { name: "Get Items From" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Add row" })).toBeVisible();
  await expect(page.getByText("Total Quantity")).toBeVisible();
});
