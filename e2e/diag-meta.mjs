// Diagnostic: log the live /meta/customer response the app receives + console errors.
import { chromium } from "@playwright/test";

const BASE = "http://localhost:5173";
const browser = await chromium.launch();
const page = await (await browser.newContext()).newPage();

page.on("console", (m) => { if (m.type() === "error") console.log("CONSOLE ERROR:", m.text()); });
page.on("response", async (r) => {
  if (r.url().includes("/meta/customer")) {
    try {
      const j = await r.json();
      console.log("META keys:", Object.keys(j).join(", "));
      console.log("META links:", JSON.stringify(j.links));
    } catch {}
  }
});

await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
await page.fill("#email", "admin@example.com");
await page.fill("#password", "ChangeMe!123");
await page.click('button[type="submit"]');
await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 15000 });
await page.goto(`${BASE}/m/customer`, { waitUntil: "networkidle" });
await page.waitForSelector("table tbody tr", { timeout: 10000 });
await page.locator("table tbody tr").first().click();
await page.waitForTimeout(2500);
await browser.close();
