# e2e — Playwright browser harness

Drives the **running** OptiERP app in a real browser so we can see and audit the
actual rendered UI (the hybrid "clone ERPNext" workflow), instead of taking
screenshots by hand. Isolated from the app: nothing here ships in the build.

## Prerequisites
- The dev app running: backend on `:8000`, frontend on `:5173`
  (`cd frontend && npm run dev`). For the Docker build use `BASE_URL=http://localhost:8080`.
- One-time install (from this folder):
  ```bash
  npm install
  npx playwright install chromium
  ```

## Hands-on commands (from `e2e/`)
| Command | What it does |
|---|---|
| `npm run capture` | Logs into **our** app, visits each route, saves `out/<name>.png` (full-page) + `out/<name>.aria.txt` (accessibility tree). |
| `npm run erpnext:login` | One-time: opens a browser, **you log into ERPNext manually**, saves the session to `auth/erpnext.json`. Your password is never stored. |
| `npm run erpnext:capture` | Captures the live ERPNext desk (reusing the saved session) to `out/erpnext/` — the reference to diff our clone against. |
| `npm run codegen` | Opens a browser and **records your clicks** into a runnable script. Best way to learn Playwright. |
| `npm test` | Runs the example specs in `tests/`. |

ERPNext site URL defaults to the staging instance; override with `ERPNEXT_URL=https://your-site.frappe.cloud`. The saved session (`auth/`) is git-ignored.

Override defaults with env vars:
```bash
BASE_URL=http://localhost:8080 npm run capture
ROUTES=/quotations/new,/sales-orders/new npm run capture
ADMIN_EMAIL=you@x.com ADMIN_PASSWORD=secret npm run capture
```

## Files
- `capture.mjs` — the screenshot + a11y-snapshot harness (standalone).
- `tests/forms.spec.ts` — example test asserting the new items grid renders.
- `playwright.config.ts` — config for the test runner / codegen.
- `out/` — capture output (git-ignored).
