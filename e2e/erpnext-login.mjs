// One-time ERPNext login. Opens a real browser window — you log in manually —
// then saves the session (cookies) to auth/erpnext.json so captures can reuse it
// headlessly. Your password is never seen or stored by the harness.
//
//   npm run erpnext:login
//   ERPNEXT_URL=https://your-site.frappe.cloud npm run erpnext:login
//
import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const AUTH = join(HERE, "auth", "erpnext.json");
const URL = process.env.ERPNEXT_URL ?? "https://erpnext-stg-elu.m.frappe.cloud";

async function main() {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await context.newPage();
  await page.goto(`${URL}/app`, { waitUntil: "domcontentloaded" });

  console.log("\n  → A browser window opened. Log into ERPNext in it.");
  console.log("    I'll save the session automatically once the desk loads (up to 5 min)…\n");

  // The Frappe desk navbar only renders once authenticated.
  await page.waitForSelector(".navbar, .page-container, .desk-sidebar", { timeout: 300000 });
  await page.waitForTimeout(1500);

  await mkdir(dirname(AUTH), { recursive: true });
  await context.storageState({ path: AUTH });
  console.log(`  ✓ Session saved to ${AUTH}`);
  console.log("    Now run:  npm run erpnext:capture\n");
  await browser.close();
}

main().catch((e) => {
  console.error("Login failed:", e.message);
  process.exit(1);
});
