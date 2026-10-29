# Phase 0 — repository audit and architecture migration

**Date:** 29 October 2026
**Target:** [`SERVERLESS_MASTER_PLAN.md`](SERVERLESS_MASTER_PLAN.md) (uploaded, approved direction)
**Decision record:** [`adr/0001-serverless-offline-first.md`](adr/0001-serverless-offline-first.md) (Proposed)

This answers the plan's §0 "first response" items (a)–(e) and the Phase 0 deliverables. It changes no application code and does not touch any device or cloud service.

## (a) Repository baseline

- Branch `claude/funny-hamilton-pfuhsz`, HEAD `9a0bed5` (merge of PR #7, `stage-a-kindle-prep`).
- Tests: `python3 -m unittest discover -s tests` → **214 tests, OK** (Linux container, venv from `requirements.txt`: Pillow 12.3.0, icalendar 7.3.0, recurring-ical-events 3.8.2, cryptography 50.0.2).
- Not run here: the three Playwright browser scripts in `tests/e2e/` (they need Node and Chromium).
- CI: **none.** There is no `.github/` directory.
- Open issues and PRs: not inspected in this pass.

## (b) Existing implementation inventory

| Area | Files | What it does today | Status |
|---|---|---|---|
| HTTP server | `app/server.py` | Stdlib `ThreadingHTTPServer`; loopback-only by default; CSRF and `Origin` checks; CSP; `/healthz`; `/api/display/frame.png` with ETag and 304 | Working, local |
| Storage | `app/store.py`, `app/validate.py` | SQLite (WAL); households, members, shopping, events, tokens, retry receipts | Working, local |
| Auth | `app/auth.py` | scrypt passwords; SHA-256-hashed session tokens (14 days); in-memory sign-in lockout | Working, local |
| Renderer | `app/render.py`, `app/frames.py`, `app/fonts/` | Deterministic 600×800 Today PNG (Pillow), bundled Lato and Noto Serif, 167 ppi metadata; atomic publish with hashes and last-good fallback | Working; physical-size acceptance pending |
| Review sheet | `app/review.py` | Printable physical-size review with 50 mm calibration | Working |
| Weather | `app/weather.py` | `FakeProvider` only; 30-minute cache; last good kept | Stub; no real provider |
| Sunset | `app/solar.py` | Computed from household location and time zone | Working |
| Daily reflection | `app/content.py`, `app/seed.json` | Verse from a local list, no network; comment says to check against a printed Bible | Working; licensing not reviewed |
| Calendar import | `app/ics.py`, `app/calendars.py` | Paste `.ics`; daily/weekly/monthly/yearly recurrence; COUNT, UNTIL, EXDATE, RDATE, moved and cancelled instances | Working |
| Calendar feeds | `app/feeds.py` | HTTPS-only feed fetch with SSRF guard (public IP pinning, no redirects, 2 MB and 10 s limits); opt-in scheduled refresh | Working, local |
| Secret storage | `app/secrets.py` | Authenticated encryption of feed URLs and cached source text with a separate owner-only key file | Working; key custody not established |
| Backup | `app/backup.py`, `app/backups.py`, `app/manage.py` | Verified SQLite snapshot; restore to new directory; revokes tokens and pauses feeds | Working, local |
| Background work | `app/server.py` workers | Minute-level household check; calendar worker | Working |
| Display client | `display_client/` | Python: bounded download, PNG/CRC validation, atomic cache, ETag, backoff, no redirects, 0600 token file | Host-only; **not on a Kindle** |
| Ops | `scripts/kfd`, `scripts/smoke.py`, `deploy/` | Setup/start/stop/smoke; Caddy and env templates | Templates only; no TLS verified |
| Phone UI | `app/index.html`, `app/static/app.js` | Vanilla JS: shopping, events, settings, preview | Working; Safari/accessibility review pending |
| Tests | `tests/*.py`, `tests/e2e/*.js` | 26 Python modules; 214 tests; browser scripts | Passing |
| Docs | `docs/*.md`, `MASTER_PLAN_V2.md`, `README.md` | Progress, install, contracts, verification reports, original plan | Accurate for the local prototype |

**Not present anywhere:** Cloudflare configuration; any Kindle-side code or package; `device/`; a JSON snapshot schema; `packages/contracts`; CI; a threat model file (partial coverage in `NETWORK_PILOT.md` and `CALENDAR_STORAGE.md`); a news adapter.

## (c) Gap analysis

Key: **Keep** = retain as is · **Modify** = change in place · **Port** = same logic in a new runtime · **Replace** = new mechanism, old one retired after parity · **Retire** = remove after migration · **Missing** = nothing exists.

| # | Capability | Current | Target (master plan) | Action | Notes |
|---|---|---|---|---|---|
| 1 | Hosting and runtime | Local stdlib server | Pages + Workers + Scheduled Workers | **Replace** | ADR-0001, decision D1. Keep the local app as a test oracle until parity. |
| 2 | Database | SQLite WAL | Cloudflare D1 | **Replace** | Needs a schema migration and a D1 export and restore procedure (missing). |
| 3 | Authentication | scrypt passwords, server sessions, CSRF | Managed auth, secure cookies, scoped tokens | **Modify / decide** | Decision D2. Household and role model is worth keeping. |
| 4 | Shopping | Add, mark got, remove; Shortcut add with request IDs | Add, complete, delete, edit, reorder; conflict-safe | **Modify** | Edit and reorder are missing. Optimistic concurrency is missing. |
| 5 | Shortcuts | Scoped, revocable tokens; retry receipts; transactional | Separately scoped tokens; no secrets in shared shortcut | **Keep / Port** | Strong existing tests; carry the behaviour across. |
| 6 | Calendar parsing and recurrence | Full local ICS expansion with tests | Read-only iCal adapter | **Port** | Python `icalendar` in Workers is **UNVERIFIED** (D1). |
| 7 | Calendar feed URL storage | Encrypted with separate key file | Feed URLs as server-only Worker secrets | **Replace** | Key-file custody and rotation do not carry over. |
| 8 | Calendar feed fetching | Python with SSRF guard | Scheduled Worker, rate-limited, cached | **Port / Replace** | Guard logic must be re-implemented and re-tested in the new runtime. |
| 9 | Weather | `FakeProvider`; 30-minute cache | Real provider adapter; scheduled caching | **Missing** (real) / **Keep** (cache policy) | Provider and licence undecided (D5). |
| 10 | Sunrise and sunset | Computed from location | Same | **Keep / Port** | Pure logic; easy port with fixtures. |
| 11 | Daily reflection | Local list | Configurable verse or quote with attribution | **Modify** | Bible text licensing and attribution not checked. |
| 12 | News headlines | None | Curated feeds with licence and excerpt rules | **Missing** | Phase 5. |
| 13 | Rendering | Server-side Pillow PNG | Kindle renders from JSON snapshot (proposed) | **Decision (D4)** | Keep the Pillow renderer as simulator and fallback until H2 is decided. |
| 14 | Kindle delivery | `GET /api/display/frame.png` with display token, ETag | Minimal, versioned, read-only JSON snapshot | **Replace** | Keep the PNG endpoint for the existing client until a snapshot client exists. |
| 15 | Kindle client | Host-only Python client | Device-side client; atomic JSON cache; last-good render | **Missing on device** | Current client is a useful reference and test oracle. |
| 16 | Snapshot schema | None (PNG contract only) | Versioned JSON schema, field limits, migration | **Missing** | Phase 2 deliverable. |
| 17 | Secrets | Env files; key file | Cloudflare secrets; `.env.example` only | **Replace** | |
| 18 | Backup and restore | Verified SQLite snapshot, restore drill | D1 export, restore and retention policy | **Modify / Missing** | Procedure must be rewritten for D1. |
| 19 | Simulator | Pillow render and review sheet | `device/simulator` 600×800 with fixtures | **Keep / Extend** | Golden-image suite is missing. |
| 20 | Tests | 214 Python tests; 3 Playwright scripts | Lint, typecheck, unit, schema, security, snapshot tests in CI | **Keep / Missing (CI)** | No CI at all today. |
| 21 | Repository layout | Flat `app/` package | `apps/`, `packages/`, `device/`, `infrastructure/` | **Do not reorganise yet** | Plan §8: document an incremental migration; no moves in Phase 0. |
| 22 | Documentation | Extensive; local-prototype scope | ADR, hardware, jailbreak review, threat model, deployment, operations, acceptance | **Modify / Missing** | This PR adds ADR, hardware, jailbreak review and this audit. Threat model, deployment, operations and acceptance docs come later. |
| 23 | Hardware | Checklist not performed | H0–H3 gates | **Keep / extend** | This PR adds `hardware-validation.md` (H0, H1) with the owner-led steps. |
| 24 | Hosting direction | `MASTER_PLAN_V2.md` and `ORIGINAL_MASTER_PLAN.md` assume Hostinger | No self-managed server | **Replace** | Conflict. The older documents keep their history; `MASTER_PLAN_V2.md` gets a pointer to the new plan. |

## (d) Risks and assumptions

| Risk | Impact | Mitigation |
|---|---|---|
| Python-to-Workers runtime mismatch (D1) | Rewriting ICS parsing, rendering and crypto costs time and can introduce defects | Spike in Phase 2: test each dependency in the chosen runtime before committing to a port |
| Kindle TLS and certificate compatibility | Wireless sync may be impossible | H3 test on the device; never weaken certificate checks; USB or manual fallback |
| Device firmware recovery route for 5.3.7.3 | Any modification could be irreversible | H1 review; owner consent; no automation |
| On-device rendering may be too slow or unstable | Display may fail or flicker | H2 proof; server PNG fallback (D4) |
| Vendor lock-in and quota changes (Cloudflare) | Cost and continuity | Usage monitoring; D1 export; documented migration plan |
| Calendar feed URL is a bearer secret | Private events exposed | Worker secret only; never in client JS or snapshot; rotation |
| Existing data migration from SQLite to D1 | Household data loss | Dry-run migration with synthetic data; verified backup before; keep local SQLite until parity |
| Loss of current working behaviour during migration | Regression | 214-test suite as oracle; port behind adapters; feature flags |
| Verse licensing | Legal exposure | Check the source's licence before any production text |

**Assumptions** (all **UNVERIFIED** until checked):
- Cloudflare's current D1, Workers, Pages and Scheduled Worker quotas and pricing support family-scale use at zero cost. Not checked in this pass.
- Managed auth providers can issue scoped tokens for iPhone Shortcuts. Not checked.
- The Kindle Touch can make HTTPS requests with a modern certificate chain. Not checked.
- Kindle 5.3.7.3 storage and clock behave as recorded in the plan. Not checked.

## (e) First PR scope (this change)

**Docs only. No application code, no tests changed, no device, no cloud service.**

| File | Change |
|---|---|
| `docs/SERVERLESS_MASTER_PLAN.md` | New: the uploaded master plan, verbatim, as the target reference |
| `docs/PHASE0_AUDIT.md` | New: this audit |
| `docs/adr/0001-serverless-offline-first.md` | New: ADR, status Proposed |
| `docs/hardware-validation.md` | New: H0 owner checklist and H1 pointer, all UNVERIFIED |
| `docs/jailbreak-recovery-review.md` | New: H1 checklist, UNVERIFIED, no method proposed |
| `MASTER_PLAN_V2.md` | One-line pointer: the target architecture is now `docs/SERVERLESS_MASTER_PLAN.md` |

**Rollback:** delete the new files and revert the pointer line. Nothing else depends on them.

**Stop gate:** the user reviews and approves the ADR, the decisions D1–D6 and the phase sequence below. The PR is not merged without approval.

## Phase sequence (proposed issues)

Each item is one PR. None starts before the previous gate passes.

| Phase | Issue (proposed title) | Gate |
|---|---|---|
| 0 | Architecture migration docs (this PR) | User approves ADR and D1–D6 |
| H0 | Owner-led non-invasive Kindle readiness record | Results recorded with redactions; no device changes |
| 2 | Snapshot JSON schema, domain fixtures, simulator screenshot and overflow tests | Schema tests pass; renderer handles missing, long, empty and stale content |
| 2a | Runtime spike: each Python dependency tested in the chosen Worker runtime (D1) | Decision recorded in ADR |
| 3 | Cloudflare Worker and D1 foundation: migrations, auth stub, shopping CRUD, snapshot endpoint, CI | Authenticated writes; read-only device reads; cross-household requests rejected |
| 4 | Pages web editor and Shortcut documentation | Two test accounts see the same list; accessibility smoke tests pass |
| 5 | Weather, sunrise, calendar, verse and news adapters with caching and attribution | Provider failure does not blank the dashboard; licence docs complete |
| H1 | Firmware-specific recovery review with sources | Owner decision on whether any device step is acceptable |
| H2 | Renderer proof on the device | Owner-approved; reversible; reboot to normal Kindle verified |
| H3 | Verified HTTPS from device, or documented fallback | Authenticated end-to-end test on the device |
| 7 | Sync client, scheduler and endurance test | 24–72-hour test including Wi-Fi loss, power loss, DST and revocation |
| 8 | Production release, runbook, handover | Owner sign-off on security, reliability, cost and device safety |

## Acceptance checklist for Phase 0

- [x] Repository inspected; baseline commit and test result recorded.
- [x] Existing work inventoried and preserved (no file deleted or moved).
- [x] Gap analysis with keep, modify, port, replace, retire and missing actions.
- [x] ADR written with open decisions and rejected alternatives.
- [x] Hardware and recovery checklists written as UNVERIFIED, with no device claims.
- [x] Phased issue list and PR scope recorded.
- [x] Owner accepts decisions D1–D6 at their stated defaults (29 October 2026).
- [ ] Owner approves the phase sequence (not yet confirmed explicitly).
- [ ] Owner confirms no device modification until H1 and explicit consent.
