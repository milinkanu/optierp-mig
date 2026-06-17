// Captures reference screenshots + a11y snapshots from the live ERPNext desk,
// reusing the session saved by erpnext-login.mjs. Output -> out/erpnext/.
// Used as the "ground truth" to diff our clone against, field by field.
//
//   npm run erpnext:capture
//   ROUTES=/app/quotation/new,/app/sales-order/new npm run erpnext:capture
//
import { chromium } from "@playwright/test";
import { access, mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const AUTH = join(HERE, "auth", "erpnext.json");
const OUT = join(HERE, "out", "erpnext");
const URL = process.env.ERPNEXT_URL ?? "https://erpnext-stg-elu.m.frappe.cloud";

const DEFAULT_ROUTES = [
  { name: "quotation-new", path: "/app/quotation/new" },
  { name: "sales-order-new", path: "/app/sales-order/new" },
  { name: "sales-invoice-new", path: "/app/sales-invoice/new" },
  { name: "delivery-note-new", path: "/app/delivery-note/new" },
  { name: "quotation-list", path: "/app/quotation" },
];

const ROUTES = process.env.ROUTES
  ? process.env.ROUTES.split(",").map((p) => ({ name: p.replace(/\W+/g, "-").replace(/^-|-$/g, ""), path: p }))
  : DEFAULT_ROUTES;

async function main() {
  try {
    await access(AUTH);
  } catch {
    console.error(`  ✗ No saved session at ${AUTH}\n    Run first:  npm run erpnext:login`);
    process.exit(1);
  }

  await mkdir(OUT, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({ storageState: AUTH, viewport: { width: 1600, height: 1000 } });
  const page = await context.newPage();

  let ok = 0;
  for (const route of ROUTES) {
    try {
      // The desk keeps a websocket open, so networkidle never fires — wait on
      // the rendered form/list instead, then let it settle.
      await page.goto(`${URL}${route.path}`, { waitUntil: "domcontentloaded", timeout: 60000 });
      await page
        .waitForSelector(".page-head, .form-layout, .list-row-container, .frappe-list", { timeout: 30000 })
        .catch(() => {});
      await page.waitForTimeout(2800);
      await page.screenshot({ path: join(OUT, `${route.name}.png`), fullPage: true });
      const snap = await page.locator("body").ariaSnapshot();
      await writeFile(join(OUT, `${route.name}.aria.txt`), snap, "utf8");
      console.log(`  ✓ ${route.path} -> erpnext/${route.name}.png`);
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
