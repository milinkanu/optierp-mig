// Capture a form route with a specific tab activated.
//   ROUTE=/purchase-orders/new TAB="Address & Contact" NAME=po-ac node capture-tab.mjs
import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "out");
const BASE = "http://localhost:5173";
const ROUTE = process.env.ROUTE ?? "/purchase-orders/new";
const TAB = process.env.TAB ?? "Address & Contact";
const NAME = process.env.NAME ?? "tab-capture";

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1600, height: 1000 } })).newPage();
await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
await page.fill("#email", "admin@example.com");
await page.fill("#password", "ChangeMe!123");
await page.click('button[type="submit"]');
await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 15000 });

await page.goto(`${BASE}${ROUTE}`, { waitUntil: "networkidle" });
await page.getByRole("button", { name: TAB, exact: true }).click();
await page.waitForTimeout(800);
await mkdir(OUT, { recursive: true });
await page.screenshot({ path: join(OUT, `${NAME}.png`), fullPage: true });
console.log(`✓ ${ROUTE} [${TAB}] -> ${NAME}.png`);
await browser.close();
