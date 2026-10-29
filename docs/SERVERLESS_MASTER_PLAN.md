# Kindle Family Dashboard — Serverless, Offline-First Master Plan

**Version:** 2.0 — architecture migration plan  
**Date:** 29 October 2026  
**Status:** Approved direction; implementation and device modifications pending validation  
**Repository:** Existing `Kindle-Family-Dashboard` repository (discover owner and exact branch from GitHub; do not assume)  
**Primary implementation agent:** Claude Code on Mac  
**Target hardware:** Amazon Kindle Touch, model D01200, firmware 5.3.7.3

---

## 0. Instructions to Claude Code — read first

You are taking over an **existing** Kindle Family Dashboard project. Your job is to migrate its plan and implementation to the architecture specified below, while preserving useful prior work. Do not assume this document describes the current repository accurately until you inspect it.

1. Inspect the full repository tree, README, existing master plan, architecture records, issues, tests, workflows, open PRs and recent merged changes. Record the baseline commit and identify work already completed.
2. Produce a **gap analysis** (keep / modify / replace / retire / missing), explicitly distinguishing current functionality from proposals. Do not destroy prior work.
3. Create or update the canonical master plan and ADRs in the repository. This file is the authoritative *target architecture*, but device compatibility and vendor availability must be verified.
4. Implement in small, independently testable phases. Create feature branches and PRs with tests, rollback notes and concise acceptance evidence. Never push directly to main or merge without user approval.
5. Never attempt jailbreak, firmware installation, system partition writes, device reset, or other potentially destructive operations automatically. Present a reviewed, firmware-specific procedure, verified sources, backups and recovery plan; require explicit user approval before each invasive action.
6. Prefer safe read-only device checks. Never log, publish or commit credentials, personal calendar data, shopping lists, serial numbers or device identifiers.
7. If a critical fact is uncertain (e.g., firmware compatibility, HTTPS capability, wake/suspend behavior, device clock), label it **UNVERIFIED** and provide a physical test instead of claiming success.
8. Do not treat USB file backup as a full firmware recovery image. Verify the available recovery method before modifying the device.
9. All external integrations must have graceful failure, sensible timeouts, caching and explicit stale-data indicators.
10. Provide runnable local commands, `.env.example`, tests, deployment steps, operational documentation and clear stop/go gates for each phase.

### First response expected from Claude Code

Before writing application code, report: (a) repo baseline, (b) existing implementation inventory, (c) proposed changes and file paths, (d) risks and assumptions, (e) proposed first PR scope. Then proceed with the approved planning PR and implementation sequence as authorised by the user.

---

## 1. Product vision and non-negotiables

Turn a desk-mounted, permanently powered Kindle Touch into an elegant, readable **family information dashboard**. Family members update information on iPhones through a simple mobile web app and optional Apple Shortcuts. The Kindle displays a cached snapshot, refreshes periodically when possible, and remains useful without Wi-Fi.

**Required modules:**
- Clock, day and date (UK local timezone with daylight-saving correctness).
- Weather conditions and short forecast.
- Daily Bible verse or quote, configurable.
- Sunrise and sunset.
- Family calendar (upcoming events, read-only on Kindle).
- Shared shopping list (add, check off, remove/reorder from phone).
- Curated news headlines.

**Product principles:**
- No self-managed always-on server, VPS, Hostinger backend, Raspberry Pi or required powered-on Mac.
- Serverless managed cloud services are acceptable; there is still a hosted API and database, but no server for the family to administer.
- Offline-first Kindle: cached display and locally maintained time when feasible.
- Mobile-first editing; Kindle is primarily read-only. Touch interaction is optional, not required for MVP.
- Modular widget/data contracts for future expansion.
- Privacy by default; no public exposure of family calendar or list data.
- Zero-cost target at ordinary family usage, subject to verification of provider quotas, billing and service changes; do not promise permanent £0 cost.
- Preserve the current GitHub repository and completed work where practical.

**Explicit non-goals for MVP:** Full calendar editing, account registration open to the public, push notifications, voice assistant, complex animations, modern browser on Kindle, running a home server, direct Kindle access to multiple third-party APIs.

---

## 2. Confirmed hardware facts and unknowns

User-confirmed from device photos and hands-on tests:

| Item | Status |
|---|---|
| Device | Amazon Kindle Touch, D01200 |
| Firmware | Kindle 5.3.7.3 (build shown in device information) |
| Display | 6-inch E Ink touchscreen; target framebuffer 600×800, **verify orientation, pixel format and effective draw area** |
| Free user storage | Approximately 3,245 MB at time of photo |
| Wi-Fi | Connects successfully |
| USB | Recognised by user's Mac |
| Development host | Mac with Claude Code |
| Power | Intended continuously plugged in; assess cable, battery health and thermal behavior |
| Custom software | User is willing, subject to safeguards |
| Amazon account | Device appears unregistered; registration is not required by product design |

**UNVERIFIED / mandatory tests:** specific jailbreak availability for firmware 5.3.7.3; whether device is already modified; safe recovery path; root/shell access; framebuffer APIs; display update commands; suspend and wake; timer reliability; wireless TLS versions and certificate store; SSH/USB networking availability; clock synchronization; charging and battery management under continuous use.

**Research sources to review, not blindly trust:** historical Kindle Touch K5 jailbreak documentation, KOReader/KUAL/MRPI compatibility matrices where relevant, and `bishopdynamics/kindle-touch-kiosk`. Pin exact versions, check maintained mirrors and provenance, inspect scripts and packages before using them. No unverified downloads or firmware changes.

### Hardware gate H0 — non-invasive readiness

- Photograph firmware/model and confirm exact model; **do not copy serial/MAC into repo**.
- Back up all user-visible USB storage to Mac and record backup location locally.
- Inventory visible folders, looking for signs of previous modification, without changing them.
- Verify safe eject and repeat USB connection; verify Wi-Fi reconnection.
- Confirm current Kindle clock/timezone and battery charging behavior.
- Record results in `docs/hardware-validation.md` with identifiers redacted.

### Hardware gate H1 — jailbreak/recovery feasibility

- Identify an installation method specifically documented for D01200 / firmware 5.3.7.3.
- Validate provenance and integrity of packages, prerequisites and compatibility.
- Document the worst-case failure modes and credible recovery paths, including whether serial console access would be necessary.
- Require explicit user consent before modifying the device.
- If no acceptable path exists, **stop** device modification and continue cloud/mobile work; offer a non-invasive fallback (manual USB image transfer or a supported replacement display).

### Hardware gate H2 — renderer proof of concept

After an approved, successful device modification:
- Display a static 600×800 monochrome test image with a safe, reversible method.
- Confirm correct rotation, contrast, ghosting, partial/full refresh and legibility.
- Confirm clean exit/reboot to standard Kindle functionality.
- Test local scheduler and screen updates at intervals; measure practical power and suspend impact.
- Demonstrate loading a local snapshot file without network access.

### Hardware gate H3 — network transport

- Verify whether the Kindle can securely fetch from the chosen HTTPS endpoint, with certificate validation.
- If old TLS is unsupported, do **not** silently disable certificate validation or expose private family data over plain HTTP.
- Evaluate a small vetted modern TLS client if supportable; otherwise consider encrypted application payload transport with proper authentication/replay protection and a threat-model review, or defer network sync and use a USB-based fallback.
- Only mark serverless wireless operation feasible after an end-to-end authenticated test on the physical device.

---

## 3. Target architecture

```text
Family iPhones / modern browsers
    |  authenticated HTTPS
    v
Cloudflare Pages (mobile-friendly family web app)
    |  HTTPS API requests
    v
Cloudflare Workers (auth, validation, read/write APIs)
    |                  |                   |
    v                  v                   v
Cloudflare D1      Scheduled Worker     External providers
family records     and caching          weather / news / calendar
    |
    v
Versioned, minimal Kindle snapshot API
    |  read-only authenticated sync, HTTPS verified on hardware
    v
Kindle Touch sync client --> atomic local JSON cache
    |
    v
Native/local lightweight e-ink renderer --> screen
```

### Service responsibilities

**Cloudflare Pages:** static assets for mobile editor; avoid client-side secrets.  
**Cloudflare Workers:** input validation, authorization, API endpoints, integration adapters, snapshot generation, request throttling, error handling.  
**Cloudflare D1:** structured family settings, shopping items, calendar-derived records where necessary, snapshots metadata and sync state.  
**Scheduled Workers:** fetch and cache weather/news/calendar with rate limits; avoid needless provider calls per Kindle refresh.  
**Kindle client:** retrieve minimal precomputed snapshot, validate, cache atomically, render, show sync/staleness status, keep last known-good data.

**Architectural preference:** precompute normalized data server-side so the Kindle needs minimal parsing and no direct third-party API access. Cloudflare's services are managed serverless infrastructure, not an absence of cloud backend services.

### Important implementation choices to validate

- Cloudflare D1 + Workers + Pages deployment and current quotas/pricing.
- Authentication provider / implementation compatible with secure browser sessions and iPhone Shortcuts. Prefer managed standards and short-lived scoped credentials; document account recovery and family invitations.
- Calendar source: choose between read-only private iCal feed and an authenticated calendar API. Private feed URLs are bearer secrets; never expose them in client JS or device snapshots. Start with an integration adapter, not a hardcoded vendor.
- Weather provider, location configuration, licensing and API terms.
- News feed source, permitted excerpts and caching policy.
- Bible verse text licensing/attribution and editorial source. Include user-authored quotes as fallback.

---

## 4. Information architecture and screens

### Kindle display — 600×800 portrait baseline

- Top: large clock; date and small last-updated / connection status.
- Weather: current condition, temperature, compact next-day outlook; sunrise/sunset.
- Calendar: next 2–4 relevant events with day/time and truncation rules.
- Shopping: next 4–7 unchecked items, count of remaining items, overflow indicator.
- Daily reflection: verse/quote with readable typography and attribution.
- News: 2–3 headlines, prioritizing readability and avoiding distracting ticker behavior.
- Footer: stale-data indicator, sync time, optional page marker.

The layout is an initial proposal; validate legibility with actual 600×800 monochrome renderings and physical device photos. Support modules being hidden, rearranged or configured in a settings schema. No module should cause overflow; graceful empty/loading/error states are required.

### iPhone family editor (responsive web app)

1. **Home:** compact preview of Kindle content and sync health.
2. **Shopping:** quick add, complete, delete, edit and reorder; optimistic UI with conflict-safe updates.
3. **Calendar:** read-only upcoming events; setup of external calendar connection in admin settings.
4. **Content:** quote/verse selection, news categories and display preferences.
5. **Settings:** timezone, location, refresh preference, module order, account management, device credential rotation, data export/delete.

Provide an Add to Home Screen-friendly mobile interface. Accessibility: readable labels, touch targets, VoiceOver semantics, high contrast and keyboard support.

### Apple Shortcuts

- `Add to Family Shopping List` — typed/dictated item; authenticated API call; clear success/failure.
- `Show Family Shopping List` — optional read-only retrieval.
- `Mark Shopping Item Complete` — optional after MVP.

Avoid tokens embedded in shared shortcut exports or query strings. Document secure credential storage and rotation; do not claim Shortcuts Keychain integration without verifying the actual implementation.

---

## 5. Data contracts

Use schema validation at every API boundary. Keep family identity separate from Kindle snapshot data. Store timestamps in UTC, render in `Europe/London` by default (configurable). Do not send sensitive auth material or external provider tokens to the Kindle.

### Example snapshot (illustrative, not a fixed API commitment)

```json
{
  "schemaVersion": 1,
  "revision": "opaque-version-id",
  "generatedAt": "2026-10-29T08:00:00Z",
  "expiresAt": "2026-10-29T08:10:00Z",
  "timezone": "Europe/London",
  "clock": { "display24h": true },
  "weather": { "temperatureC": 12, "summary": "Cloudy", "forecast": [] },
  "sun": { "sunrise": "07:00", "sunset": "16:45" },
  "calendar": { "events": [] },
  "shopping": { "remainingCount": 0, "items": [] },
  "reflection": { "text": "", "source": "" },
  "news": { "headlines": [] },
  "modules": ["clock", "weather", "calendar", "shopping", "reflection", "news"]
}
```

Values above are placeholders only, **not actual weather or sunrise times**. Final contract must specify field limits, max string length, sanitization, optional data, locale, schema migration, stale thresholds, content licensing, atomic cache writes, and compatibility between deployed API and installed Kindle client.

### Suggested entities

`Family`, `Member`, `Device`, `ShoppingItem`, `ModulePreference`, `IntegrationConfig`, `CalendarEventCache`, `WeatherCache`, `NewsCache`, `SnapshotRevision`, `AuditEvent` (minimal, privacy-conscious). Use D1 migrations, indices, ownership checks and a documented retention/deletion policy.

### API surface (proposed)

- `GET /api/me` — signed-in browser identity.
- `GET /api/shopping` — family-authorized list.
- `POST /api/shopping` — add item.
- `PATCH /api/shopping/:id` — update or complete item.
- `DELETE /api/shopping/:id` — remove item.
- `GET /api/calendar/upcoming` — normalized events.
- `GET/PATCH /api/preferences` — configuration.
- `GET /api/device/snapshot` — **read-only device-scoped** response, conditional retrieval via ETag/version where practical.
- `POST /api/admin/devices/rotate` — admin-only device credential rotation.
- `GET /api/health` — operational health, no private content.

Use consistent error schema, pagination/limits, idempotency for shortcut additions where possible, request rate limiting and authorization on every family-owned record.

---

## 6. Security and privacy requirements

1. All family-facing traffic uses authenticated HTTPS. Verify device HTTPS behavior rather than assuming it.
2. Device credential is read-only, scoped to one family/device, revocable and rotatable. Never share mobile admin credentials with the Kindle.
3. Server-side family authorization on **every** query/mutation; no trusting family IDs supplied by clients.
4. No publicly accessible family snapshots, D1 databases, calendar URLs, tokens or shopping data.
5. Secrets stored in Cloudflare secret management; local development uses ignored env files; commit only `.env.example`.
6. Browser sessions use secure, HttpOnly, SameSite cookies and CSRF defenses where applicable; Shortcuts use separately scoped tokens.
7. Validate and limit inputs, escape rendered text, enforce CSP/CORS policies, and implement sensible throttling.
8. Keep only minimum calendar information required; support retention, export and deletion. Review applicable UK privacy obligations and providers' data processing terms before production.
9. Audit only meaningful security actions, avoiding full private payloads and unnecessary IP/device identifiers.
10. Include threat-model notes for lost iPhone, stolen Kindle, leaked shortcut token, exposed calendar URL, compromised family account, API outage and credential rotation.
11. Do not put family data in GitHub Actions logs, PR screenshots, public preview environments or analytics.
12. Ensure backup/restore strategy for D1 and document service lock-in and export path.

---

## 7. Reliability, scheduling and e-ink constraints

**Five-minute refresh is a target, not a promise** until physical tests verify scheduling, wake behavior and battery impact. Prefer refresh only when content changes; avoid full-screen flashes where partial refresh is safe. Periodically full-refresh to control ghosting based on observed behavior.

- Separate content refresh frequencies: clock display can update locally; weather/news/calendar update according to provider and device needs; shopping can update every successful sync.
- Cache each provider's data cloud-side; Kindle fetches a single small snapshot.
- Retry transient failures with bounded exponential backoff and jitter; never enter a busy loop.
- Keep last known-good snapshot and use atomic replace (write temp, validate, rename).
- Show a subtle last-updated/stale indicator when information exceeds module-specific freshness limits.
- On reboot, render cache before attempting network access.
- Monitor power draw, charging temperature and suspend/resume behavior. Avoid untested battery bypass or permanent hardware modifications.
- Support a safe disable/uninstall path and a manual USB sync fallback.

---

## 8. Repository organisation (adapt to existing repo)

```text
/
  README.md
  MASTER_PLAN.md                  # canonical updated master plan, or retain existing path
  docs/
    adr/
      0001-serverless-offline-first.md
      0002-device-sync-security.md
      0003-calendar-integration.md
    hardware-validation.md
    jailbreak-recovery-review.md
    threat-model.md
    deployment.md
    operations.md
    acceptance-tests.md
  apps/
    family-web/                   # mobile-first editor
    api/                          # Cloudflare Worker
  packages/
    contracts/                    # shared JSON schemas and TS types
    core/                         # portable domain logic
  device/
    kindle-touch/                 # lightweight renderer, sync and packaging
    simulator/                    # desktop 600x800 preview / fixture runner
  infrastructure/
    cloudflare/                   # Wrangler configuration, D1 migrations
  shortcuts/
    README.md                     # documented actions, no secrets
  tests/
    fixtures/                     # synthetic, non-personal test data
  .github/workflows/
```

Do not reorganize a working repository merely for aesthetic consistency. If current structure differs, document an incremental migration and preserve imports, tests and history.

---

## 9. Implementation roadmap and validation gates

### Phase 0 — repository audit and architecture migration (first PR)

**Deliverables:** inventory, gap analysis, updated master plan, ADR, risks, phased issues, acceptance checklist, existing work preservation plan.  
**Gate:** user approves target architecture and first implementation sequence; no device modifications.

### Phase 1 — hardware research and safe validation (parallel)

**Deliverables:** device test checklist, firmware-specific jailbreak/recovery assessment, non-invasive checks, static renderer plan.  
**Gate:** H0 and H1 documented. Never imply a working jailbreak before physical proof.

### Phase 2 — contracts, local simulator and test fixtures

**Deliverables:** versioned snapshot JSON schema, domain models, 600×800 monochrome simulator, deterministic fixtures, screenshot/overflow tests.  
**Gate:** renderer handles missing, long, empty and stale content; schema tests pass; no Kindle modification needed.

### Phase 3 — Cloudflare backend foundation

**Deliverables:** Worker, D1 migrations, API validation, auth integration, shopping CRUD, snapshot endpoint, local dev setup, CI tests, secrets handling.  
**Gate:** authenticated browser writes; read-only device reads; unauthorized access rejected; database migrations reproducible; no personal data in test fixtures.

### Phase 4 — iPhone web editor and Shortcuts

**Deliverables:** responsive shopping interface, home preview, preferences, calendar read-only integration setup, documented Shortcut, onboarding and recovery.  
**Gate:** two family test accounts see the same list; updates persist; account separation works; no secrets in shared shortcut; accessibility smoke tests pass.

### Phase 5 — integrations and caching

**Deliverables:** weather, sunrise/sunset, calendar, verse/quote and news adapters; scheduled caching; attribution and licensing documentation.  
**Gate:** provider failure does not blank dashboard; rate limits respected; all content has correct timezone and source attribution.

### Phase 6 — Kindle custom software and renderer

**Prerequisite:** user-approved H1; device modification must not be automated.  
**Deliverables:** reproducible device package, safe installation procedure, local cache renderer, rollback instructions, physical-device evidence.  
**Gate:** H2 passes; reboot/recovery verified; no unapproved firmware writes.

### Phase 7 — secure wireless sync and endurance testing

**Prerequisite:** H3 transport verified.  
**Deliverables:** authenticated snapshot sync, conditional fetch, retries, stale indicators, scheduler, USB fallback, operational diagnostics.  
**Gate:** 24–72-hour observed test including Wi-Fi loss/recovery, power interruption, daylight-saving/time handling, device reboot and token revocation. Log measured behavior rather than assuming exact 5-minute refresh.

### Phase 8 — production release and handover

**Deliverables:** stable deployment, owner documentation, restore/rollback, family onboarding, device credential rotation, cost monitoring, privacy checklist, future roadmap.  
**Gate:** user sign-off on security, reliability, costs, device safety and end-to-end acceptance.

---

## 10. Pull request and release policy

- One coherent change per PR; use descriptive branches such as `docs/serverless-architecture`, `feat/contracts-simulator`, `feat/cloudflare-api`, `feat/family-web`, `feat/kindle-renderer`.
- Each PR must include: purpose, changed files, tests run and results, risks, manual test instructions, screenshots when relevant, rollback and follow-up issues.
- CI should run lint/typecheck, unit tests, schema validation, security checks and simulator snapshot tests where supported.
- Protect `main`; do not auto-merge without user authorization.
- Pin dependencies and audit supply chain; avoid unreviewed executable scripts, especially Kindle modification packages.
- Maintain compatibility between current Kindle client and API during rolling deployment; version contracts and migrations.
- Do not commit secrets, personal device IDs, real calendar content or personal shopping data.

---

## 11. End-to-end acceptance criteria

1. A family member can add an item from an iPhone browser; another family member can see it and mark it complete.
2. The same item appears on the Kindle after the next successful authenticated sync, subject to verified device capabilities.
3. Family calendar events display with correct UK local times, including DST transitions.
4. Weather, sunrise/sunset, daily reflection and news are legible and have fallback states.
5. A loss of Wi-Fi does not prevent displaying cached information; stale content is clearly marked.
6. Restarting the Kindle recovers the last valid dashboard without corruption.
7. The Kindle cannot edit shopping items or retrieve private admin data with its device credential.
8. Revoking the Kindle credential stops future syncs while preserving existing local cache until intentionally cleared.
9. Unauthenticated and cross-family API requests cannot access private records.
10. The system can be deployed and operated without a home server, always-on Mac or Hostinger backend.
11. Normal family usage fits within agreed cost thresholds; alarms or documentation cover quota/billing changes.
12. Installation and rollback are documented, and the user explicitly approves any invasive device operation.

---

## 12. Risks and contingency plans

| Risk | Mitigation / fallback |
|---|---|
| No safe firmware 5.3.7.3 jailbreak path | Stop device changes; continue web/cloud; manual USB transfer or alternate supported display |
| Old Kindle TLS incompatible | Test vetted modern TLS client; do not weaken certificate validation; USB fallback |
| Kindle suspend prevents 5-minute refresh | Measure wake behavior; use practical adaptive schedule, or adjust user expectation |
| E-ink ghosting / wear | Minimize unnecessary refreshes; empirically tune full vs partial refresh |
| Cloudflare free-tier changes | Usage monitoring, exportable D1 data, documented cost cap and migration plan |
| Calendar feed leaks | Server-only encrypted secrets, least privilege, rotation, never client-exposed |
| Device theft | Read-only scoped token, remote revocation, minimal snapshot, local-data disclosure assessment |
| Third-party API outage | Cache and stale indicators; provider adapter substitution |
| Hardware failure from modification | Firmware-specific recovery research and user consent before any invasive action |

---

## 13. Immediate work package for Claude Code

**Start with planning and repository preservation, then implement the next two safe phases.**

1. Inspect repository and summarize current code, previous master plan and merged work.
2. Create `docs/adr/0001-serverless-offline-first.md` and update the canonical master plan with this architecture.
3. Create `docs/hardware-validation.md` and `docs/jailbreak-recovery-review.md` as explicit UNVERIFIED checklists, not invented confirmations.
4. Define the first versioned snapshot schema and synthetic fixtures.
5. Build a desktop 600×800 monochrome dashboard simulator, reusing any existing renderer or UI assets where appropriate.
6. Add tests and CI for the schema/simulator.
7. Open a PR with a detailed diff summary and validation evidence; **stop for review before merge**.
8. Propose the next PR for Cloudflare Worker + D1 foundation, with security and local development design.

**Do not:** jailbreak the Kindle, deploy a live cloud service, request or expose credentials, replace existing architecture indiscriminately, or merge the PR without approval.

### Suggested initial Claude Code prompt

> Read `Kindle_Family_Dashboard_Serverless_Master_Plan.md` and audit this existing repository against it. Preserve useful merged work. First give me the baseline inventory, gap analysis and exact proposed PR scope. Then implement the Phase 0 architecture migration and Phase 2 snapshot-contract/simulator groundwork on a feature branch, with tests and documentation. Open a pull request but do not merge. Do not modify the physical Kindle or deploy Cloudflare yet. Flag every firmware-specific claim as unverified until supported by authoritative evidence and device testing.

---

## 14. Decisions to revisit only when needed

- Family authentication provider and number of family accounts.
- Calendar provider (Apple shared calendar, Google Calendar, or another source) and authorization approach.
- Weather location and provider.
- Reflection source and Bible translation licensing.
- News sources and categories.
- Whether Kindle touch controls are needed beyond initial display.
- Hosting domain (Cloudflare subdomain versus custom domain).
- Final physical mounting and power management strategy.

**Default rule:** choose the simplest secure, reversible option and make it configurable. Do not block early simulator/backend development on optional preferences.
