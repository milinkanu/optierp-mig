// Capture harness — logs into the running OptiERP dev app and saves, per route,
// a full-page screenshot + an accessibility (a11y) snapshot. Outputs land in
// e2e/out/ for review/audit. Touches no app code; read-only against the UI.
//
//   node capture.mjs                                   # default routes @ :5173
//   BASE_URL=http://localhost:8080 node capture.mjs    # against the Docker build
//   ROUTES=/quotations/new,/sales-orders/new node capture.mjs
//
import { chromium } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "out");

const BASE_URL = process.env.BASE_URL ?? "http://localhost:5173";
const EMAIL = process.env.ADMIN_EMAIL ?? "admin@example.com";
const PASSWORD = process.env.ADMIN_PASSWORD ?? "ChangeMe!123";

// Default capture set — override with ROUTES=/a,/b (name is derived from path).
const DEFAULT_ROUTES = [
  { name: "quotation-new", path: "/quotations/new" },
  { name: "sales-order-new", path: "/sales-orders/new" },
  { name: "sales-invoice-new", path: "/sales-invoices/new" },
  { name: "purchase-order-new", path: "/purchase-orders/new" },
  { name: "purchase-invoice-new", path: "/purchase-invoices/new" },
  { name: "quotations-list", path: "/quotations" },
  { name: "selling-workspace", path: "/selling" },
];

const ROUTES = process.env.ROUTES
  ? process.env.ROUTES.split(",").map((p) => ({ name: p.replace(/\W+/g, "-").replace(/^-|-$/g, ""), path: p }))
  : DEFAULT_ROUTES;

async function login(page) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: "networkidle" });
  await page.fill("#email", EMAIL);
  await page.fill("#password", PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 15000 });
}

async function main() {
  await mkdir(OUT, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
  const page = await context.newPage();

  console.log(`Logging in at ${BASE_URL} as ${EMAIL}…`);
  await login(page);

  let ok = 0;
  for (const route of ROUTES) {
    try {
      await page.goto(`${BASE_URL}${route.path}`, { waitUntil: "networkidle" });
      await page.waitForTimeout(800); // let async data settle
      await page.screenshot({ path: join(OUT, `${route.name}.png`), fullPage: true });
      const snap = await page.locator("body").ariaSnapshot();
      await writeFile(join(OUT, `${route.name}.aria.txt`), snap, "utf8");
      console.log(`  ✓ ${route.path} -> ${route.name}.png`);
      ok += 1;
    } catch (e) {
      console.error(`  ✗ ${route.path}: ${e.message}`);
    }
  }

  await browser.close();
  console.log(`\nDone: ${ok}/${ROUTES.length} captured. Output in ${OUT}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
