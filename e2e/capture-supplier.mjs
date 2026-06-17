import { chromium } from "@playwright/test";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const OUT = join(dirname(fileURLToPath(import.meta.url)), "out");
const BASE = "http://localhost:5173";
const b = await chromium.launch();
const p = await (await b.newContext({ viewport: { width: 1600, height: 1000 } })).newPage();
await p.goto(`${BASE}/login`, { waitUntil: "networkidle" });
await p.fill("#email", "admin@example.com"); await p.fill("#password", "ChangeMe!123");
await p.click('button[type="submit"]');
await p.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 15000 });
await p.goto(`${BASE}/m/supplier`, { waitUntil: "networkidle" });
const rows = await p.locator("table tbody tr").count();
console.log("supplier rows:", rows);
if (rows > 0) {
  await p.locator("table tbody tr").first().click();
  await p.waitForURL(/\/m\/supplier\/[0-9a-f-]+/i, { timeout: 10000 });
  await p.waitForSelector("text=Addresses", { timeout: 8000 }).catch(() => {});
  await p.waitForTimeout(1200);
  await p.screenshot({ path: join(OUT, "supplier-edit.png"), fullPage: true });
  console.log("captured supplier-edit ->", p.url());
}
await b.close();
