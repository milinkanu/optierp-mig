// One-off: log into our app, open the first Customer, and screenshot the edit
// page to confirm the inline Address & Contact (LinkedRecords) section renders.
import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "out");
const BASE = process.env.BASE_URL ?? "http://localhost:5173";
const EMAIL = process.env.ADMIN_EMAIL ?? "admin@example.com";
const PASSWORD = process.env.ADMIN_PASSWORD ?? "ChangeMe!123";

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1600, height: 1000 } })).newPage();
await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
await page.fill("#email", EMAIL);
await page.fill("#password", PASSWORD);
await page.click('button[type="submit"]');
await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 15000 });

await page.goto(`${BASE}/m/customer`, { waitUntil: "networkidle" });
await page.waitForSelector("table tbody tr", { timeout: 10000 });
await page.locator("table tbody tr").first().click();
await page.waitForURL(/\/m\/customer\/[0-9a-f-]+/i, { timeout: 10000 });
await page.waitForSelector("text=Addresses", { timeout: 10000 }).catch(() => {});
await page.waitForTimeout(1200);
await mkdir(OUT, { recursive: true });
await page.screenshot({ path: join(OUT, "customer-edit.png"), fullPage: true });
console.log("✓ customer edit page ->", page.url());
await browser.close();
