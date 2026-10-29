# Phase 3 — Cloudflare Worker and D1 foundation

**Date:** 29 October 2026 · **Status:** implemented and tested locally. **Not deployed.** No Cloudflare account, production secret, sign-in provider or public hostname has been created.
**Gate (plan §9):** authenticated browser writes; read-only device reads; unauthorised access rejected; migrations reproducible; no personal data in fixtures.

## What exists

| Path | Purpose |
|---|---|
| `infrastructure/cloudflare/migrations/0001_init.sql` | D1 schema: households, members, sessions, devices, api_tokens, shopping_items |
| `infrastructure/cloudflare/wrangler.toml` | Worker and D1 binding (local development values) |
| `infrastructure/cloudflare/.dev.vars.example` | Local-only variables; copy to `.dev.vars`, which is git-ignored |
| `apps/api/src/worker.ts` | Router and error handling |
| `apps/api/src/handlers.ts` | Route handlers; every query filters on `household_id` |
| `apps/api/src/auth.ts` | Session, CSRF and device-credential checks |
| `apps/api/src/http.ts`, `env.ts` | Responses, body limits, binding types |
| `packages/core/src/` | Portable logic: tokens, input rules, snapshot builder |
| `apps/api/test/` | 45 tests; real handlers and real migration SQL |
| `.github/workflows/ci.yml` | Python prototype tests; Worker typecheck, tests and migration check |

## Endpoints

| Method and path | Who may call it | Notes |
|---|---|---|
| `GET /api/health` | Anyone | `{"ok": true}` only |
| `GET /api/me` | Signed-in member | Returns role and CSRF token |
| `POST /api/dev/login` | **Local environment only** | Returns 404 in every other environment |
| `POST /api/logout` | Member, with CSRF | |
| `GET /api/shopping` | Member | Household list, ordered by position |
| `POST /api/shopping` | Member (CSRF) or Shortcut token (`shopping:add`) | Title 1–60 characters |
| `PATCH /api/shopping/:id` | Member, with CSRF | Requires the current `version`; 409 with the current item if stale |
| `DELETE /api/shopping/:id?version=N` | Member, with CSRF | Same conditional rule |
| `GET /api/device/snapshot` | Display token (`snapshot:read`) | Contract v1; ETag = revision; 304 when unchanged |
| `POST /api/admin/devices` | Admin, with CSRF | Creates a device and returns its token once |
| `POST /api/admin/devices/:id/rotate` | Admin, with CSRF | Revokes old tokens; returns a new one |
| `DELETE /api/admin/devices/:id` | Admin, with CSRF | Immediate revocation |

## Security controls, and where they are tested

| Control | Test |
|---|---|
| Household identity comes from the stored credential, never the body | `the body cannot choose the household` |
| Cross-household reads and writes are refused (404) | `one household cannot read or change another household's item` |
| Session cookie: HttpOnly, Secure, SameSite=Strict | `session cookie is HttpOnly, Secure and SameSite=Strict` |
| Browser writes need the exact origin and CSRF token | `browser writes need the CSRF token and the exact origin` |
| Sessions expire and can be ended | `an expired session is rejected`, `logout invalidates the session` |
| Display credential cannot read or change the list | `a display credential cannot read or write the shopping list` |
| Shortcut credential can add only | `a shortcut credential can add but not read the list or fetch the snapshot` |
| Revocation and rotation take effect at once | `a revoked device stops working immediately`, `rotating a device invalidates the old token…` |
| Tokens and sessions stored only as SHA-256 hashes | `device tokens are stored only as hashes` |
| Snapshot exposes no tokens, household IDs or member names | `the snapshot holds only the shopping list…` |
| Dev sign-in disabled outside `ENVIRONMENT=local` | `dev sign-in is refused outside the local environment` |
| Concurrent edits: exactly one wins; stale edits are refused with the current item | `concurrent writes from the same version…`, `a stale PATCH is refused…` |
| Body limits and JSON-only input | `bodies must be JSON objects under the size limit` |
| Errors do not leak internals | `unhandled error` path logs only the error name |

## Migrations

- `0001_init.sql` is the only migration. Two fresh databases produce identical schemas (test `migration is reproducible`).
- Applied to a local D1 database with `wrangler d1 migrations apply kfd --local`: succeeded.
- The schema enforces its own limits too (title length, enum values), so bad data is refused below the application layer.

## Local end-to-end run (evidence)

`wrangler dev --local` (Wrangler 4.155.0, workerd), real HTTP:

| Step | Result |
|---|---|
| Dev sign-in | 200, cookie with HttpOnly; Secure; SameSite=Strict |
| Write without CSRF | 403 |
| Write with another origin | 403 |
| Valid write | 201 |
| List | Both items, in order |
| Create display credential | Token returned once |
| Snapshot | 200, ETag set |
| Snapshot with matching `If-None-Match` | 304 |
| Shopping list with display credential | 401 |
| Shopping list with no credential | 401 |

The device token and session cookie were not written to any file in the repository.

## Gaps and decisions still open

1. **Production sign-in (ADR D2) is not chosen.** There is no production sign-in route, so the deployed Worker would have no browser users. This blocks deployment. Local dev login is a stand-in only.
2. **Reordering is a sort key.** A client moving an item must set positions for every item it moves. A server-side "move to top" does not exist yet, and ties fall back to creation order.
3. **No idempotency for Shortcut adds.** The existing Python prototype has request IDs for retries. Not yet ported.
4. **No rate limiting.** Plan §5 requires throttling. Cloudflare rate-limit rules or a Durable Object limiter must be chosen.
5. **Calendar, weather, news, verse and preferences endpoints** are later phases (5 and 4). The snapshot contains only the shopping list; other modules are null or empty as the contract allows.
6. **No production secrets, account or domain.** `PUBLIC_ORIGIN` for production and the `database_id` in `wrangler.toml` are placeholders.
7. **Audit events** (plan §6 item 9) are not implemented.
8. **Free-plan CPU limits** are unverified (see `D1-runtime-spike.md`). The handlers do a few queries each, which should be well within limits, but this is not measured in production.
9. **Local data:** the local D1 database, and the `.dev.vars` file, are git-ignored and never leave the machine.

## Rollback

Delete `apps/api/`, `packages/core/`, `infrastructure/cloudflare/`, `.github/workflows/ci.yml`, and this document, then revert the `.gitignore` lines. Nothing else depends on them.
