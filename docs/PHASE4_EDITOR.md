# Phase 4 — phone editor and Shortcut

**Date:** 29 October 2026 · **Status:** built and tested against the local Worker. **Not deployed.** Sign-in is development-only until ADR D2 is decided.
**Gate (plan §9):** two family accounts see the same list; updates persist; account separation works; no secrets in a shared Shortcut; accessibility smoke tests pass.

## What was built

| Path | Purpose |
|---|---|
| `apps/family-web/index.html`, `app.js`, `styles.css` | Static phone editor: no build step, no framework, no inline script or style |
| `apps/family-web/_headers` | Content-Security-Policy and security headers for the editor |
| `apps/family-web/e2e/run.mjs` | Browser checks (two accounts, reorder, conflicts, device management, phone layout, accessibility) |
| `apps/api/src/worker.ts` (additions) | `GET /api/snapshot/preview`, `GET /api/admin/devices`, `signIn` status in `/api/health`, display name in `/api/me` |
| `infrastructure/cloudflare/wrangler.toml` (addition) | `[assets]`: the Worker serves the editor on the same origin as the API |
| `shortcuts/README.md` | The "Add to Family Shopping List" Shortcut, with no secrets |

### Screens

- **Sign in:** shown when there is no session. In production it says sign-in is not set up yet.
- **Home:** a preview of what the Kindle receives (date, shopping count, items, generated time). It is marked stale after 20 minutes.
- **Shopping:** add, mark got, rename, move up or down, and delete. Each write is version-checked. A conflict reloads the list and asks the member to try again.
- **Calendar:** a placeholder. Calendar integration is Phase 5.
- **Settings:** account, sign out, and for admins: create, rotate and revoke device tokens. A new token is shown once, with a copy button.

## Gate evidence

| Gate item | Evidence |
|---|---|
| Two family accounts see the same list | Browser test: Alex adds an item; Sam sees it |
| Updates persist | Completion by Sam is visible to Alex after reload |
| Stale changes are refused, not overwritten | Browser test: Sam's out-of-date page gets a clear conflict message; Worker tests `a stale PATCH is refused` and `concurrent writes…` |
| Account separation | Members do not see device management; a display token cannot read the list; another household's devices are not listed |
| No secrets in the shared Shortcut | `shortcuts/README.md` contains placeholders only. The served HTML and JavaScript are checked for `kfd_` in a browser test. |
| Accessibility smoke test | axe-core, WCAG 2 A and AA rules, run on sign-in, home, shopping, calendar and settings (admin and member). Zero violations. |
| Phone layout | No horizontal scroll at iPhone 13 emulation on every screen |
| Security headers | CSP `default-src 'self'` on the editor; API responses keep `no-store` and `default-src 'none'` |

Results: `node e2e/run.mjs` → **23 passed, 0 failed**, run three times in succession. The Worker suite has **50 passing tests** (`npm test` in `apps/api`).

## How to run locally

```bash
cd apps/api
npm run db:migrate:local
npx wrangler d1 execute kfd --local --config ../../infrastructure/cloudflare/wrangler.toml --command \
  "INSERT OR REPLACE INTO households (id,name,timezone,created_at) VALUES ('e2e-h','E2E family','Europe/London','2026-10-29T00:00:00Z'); \
   INSERT OR REPLACE INTO members (id,household_id,display_name,role,created_at) VALUES ('e2e-admin','e2e-h','Alex','admin','2026-10-29T00:00:00Z'),('e2e-member','e2e-h','Sam','member','2026-10-29T00:00:00Z');"
npm run dev          # serves the editor and API at http://localhost:8787
# in another terminal:
cd ../family-web
KFD_BASE=http://localhost:8787 node e2e/run.mjs
```

The browser test uses Playwright and Chromium. It loads Playwright with `require`, so it needs a Playwright installation that the test process can resolve. It is not in CI yet (see gaps).

## Decisions and deviations to confirm

1. **Same-origin hosting through the Worker, not a separate Cloudflare Pages project.** The cookie and CSRF rules need the editor and API to share an origin. Pages with a route to the same hostname would do the same job. Confirm before deployment.
2. **Pessimistic updates.** The plan asked for optimistic UI. The editor waits for the server and then reloads, which is simpler and matches the conflict rule. Optimistic updates can be added once the flow is in daily use.
3. **Reordering is a full renumbering.** Moving an item sends one version-checked write per item whose position changes. These writes are not one transaction. If one fails, the list reloads and shows the conflict.
4. **Refresh.** The list refreshes when a tab opens and when the phone's page comes back into view. There is no live push.

## Gaps (not yet built, or not verified)

- **Real iPhone testing.** Only Chromium with iPhone 13 emulation was used. Safari, VoiceOver and Dynamic Type were not tested. The plan's Safari and accessibility review remains open.
- **Production sign-in (ADR D2).** Browser users cannot sign in on a deployed server yet. The development sign-in is local only.
- **Settings for timezone, location, refresh and module order** are not implemented. The household timezone is set in the database only.
- **Calendar and weather** are placeholders. Phase 5.
- **Browser tests are not in CI.** They need Chromium, and the Playwright setup needs to be fixed in the repository before they can run in CI.
- **Shortcut retries** can add an item twice; the Shortcut guide says so.
- **Shortcut token storage on iOS** is not verified.

## Rollback

Delete `apps/family-web/`, `shortcuts/`, this document, the `[assets]` block in `wrangler.toml`, and the editor-related routes in `apps/api/src/worker.ts`. The Phase 3 API keeps working without them.
