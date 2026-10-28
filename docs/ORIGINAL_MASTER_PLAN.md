# Kindle Family Display — Claude Code Master Plan

**Version:** 1.0  
**Prepared:** 28 October 2026  
**Status:** Approved product direction; implementation may begin in safe software-only stages. Device modification requires a separate explicit approval.  
**Primary device:** Amazon Kindle Touch (D01200, Kindle Touch / K5, 4th-generation era)  
**Working name:** Kindle Family Display  
**Development environment:** Mac + Claude Code + Git  
**Preferred eventual hosting:** Existing Hostinger account, if runtime/network support is validated.

> **Instruction to Claude Code:** Treat this document as the authoritative product and engineering brief. You may plan, scaffold, implement, and test the **server, mobile Family Hub, modular renderer, mock display and Apple Shortcuts API**. DO NOT jailbreak, flash, update, root, modify, wipe, or run installation commands against the physical Kindle without a new explicit user instruction after the hardware gate. Do not deploy to production or expose services publicly without approval. Do not assume that this machine has the Kindle attached, Hostinger access, or credentials. Document assumptions, run local tests, and stop at each gated milestone.

---

## 1. Vision and outcome

Turn a 2011 Kindle Touch D01200 into a **calm, readable, predominantly static, touch-switchable family information display** on a desk or shelf. The device should feel purpose-built: elegant black-and-white typography; no unnecessary browser chrome; near-zero processing on the Kindle; and a reliable five-minute check for changes.

Family members should update the content from an iPhone using a **responsive Family Hub web application** and **Apple Shortcuts**. Kindle-side interaction should initially be limited to switching pages; adding or editing shopping-list items belongs on the phones. The software must remain useful even if this Kindle cannot be modified safely: the full system should have a browser simulator and image exports, and could later serve another display.

### Fixed user decisions

| Dimension | Requirement |
|---|---|
| Purpose | Family information hub |
| Physical placement | Desk or shelf; portrait |
| Screen | Kindle Touch D01200, 600 × 800 e-ink, 16-level greyscale target |
| Information | Clock/date, weather forecast, daily quote or Bible verse, sunrise/sunset, family calendar, shopping list, news headlines |
| Interaction | Hybrid: automatic refresh, touch page navigation if technically proven |
| Power | Plugged in; must assess aged battery and charging safety |
| Refresh | Check for changes every five minutes when awake and connected; redraw only if needed |
| Information entry | Family Hub web interface and iPhone Shortcuts |
| Extension model | Modular data adapters and widgets; additional pages/devices later |
| Coding | Claude Code on Mac; incremental implementation; tests and documentation |
| Firmware | No changes until exact firmware, recovery and battery safety are assessed |

### Non-goals for MVP

- Building a new Kindle operating system or Linux distribution.
- Running a modern browser, React frontend, calendar provider SDK, or third-party API integrations directly on the Kindle.
- Playing media, viewing videos, or displaying news articles in full.
- Editing shopping lists directly on the e-ink screen.
- Creating an open, unauthenticated family-data endpoint.
- Automatically signing into or scraping Apple iCloud, Google, Microsoft, or news websites.
- Purchasing new hardware before a feasibility decision.

---

## 2. System overview and architecture

Implement **three user-facing components** and an optional connectivity bridge:

1. **Family Hub (PWA-style mobile web app):** login, shopping, family calendar, daily content, news feeds, display configuration, member access and device health. Optimise for iPhone Safari; browser installation is optional.
2. **Family API + backend services:** user/household permissions, database, external API adapters, scheduling, shortcut endpoints, image rendering, frame manifests and diagnostics.
3. **Kindle display client:** eventual minimal script/native utility that polls a local or compatible gateway, downloads a pre-rendered image only on change, displays it, and optionally handles touch navigation. **Not implemented or installed until device feasibility is approved.**
4. **Optional local Kindle bridge:** if Kindle-era TLS/CA/ciphers are inadequate, a device-isolated local bridge retrieves frames via modern TLS, then serves a strictly limited display-only interface to the Kindle. The bridge must never expose editing routes or upstream secrets. Cloud application remains the canonical source of data.

### Logical flow

```text
iPhone browser ──HTTPS──┐
                       ├── Family API ── database
Apple Shortcuts ─HTTPS─┘       │
                              ├── weather / solar API
                              ├── external calendar adapters (optional)
                              ├── curated RSS feeds
                              └── content renderer → versioned 600×800 frames
                                                      │
                        modern HTTPS OR approved local display bridge
                                                      │
                                              Kindle D01200
                                      (display / page navigation only)
```

### Design principles

- **Phone-first input, e-ink-first output.** No one needs to enter text on the Kindle.
- **Server-rendered frames.** No JavaScript runtime needed on the e-reader.
- **Least privilege.** Kindle cannot create/change household data; shortcuts have narrow permissions.
- **Deterministic, cacheable output.** Same inputs + settings give same image; hash changes only when visible output changes.
- **Offline/degraded behaviour.** Previously rendered screens stay visible during an outage; mobile edits still work while Kindle is offline.
- **Configurable modules.** A module provides data and rendering components, not arbitrary third-party code executed on the Kindle.
- **No hidden security downgrades.** Never disable TLS verification to make the Kindle connect.

---

## 3. Hardware facts, unknowns, and research sources

**Identified model:** Kindle Touch D01200 / Kindle Touch (4th generation). Working target is a 6-inch 600×800 E Ink Pearl display with 16 grayscale shades and 256 MB RAM; verify particular unit and system details in the audit.

**Firmware:** Amazon's current support page lists **5.3.7.3** as the final software release for Kindle Touch (4th Generation). Earlier firmware versions may require intermediate upgrades. **This is a fact to record, not permission to update.**

**Community precedent:** `bishopdynamics/kindle-touch-kiosk` explicitly targets Kindle Touch D01200 and documents a jailbreak + KUAL + USB networking + VNC client, with Chromium and VNC server running elsewhere. This supports feasibility of some touch-based kiosk interactions. It does **not** establish that its packages are secure, current, reversible, licensed for reuse, or compatible with the specific Kindle in hand. The project's VNC architecture is a reference/fallback, not automatically our production choice.

**Before any device operation, verify:** firmware/build, storage visibility, available backups, battery swelling/heat/charging stability, Wi-Fi network compatibility, USB data path, physical buttons/touch, screen damage, supported recovery procedure, and trusted sources/known hashes for any contemplated packages.

**References (verify again when implementation reaches relevant stage):**
- Amazon Kindle updates: https://digprjsurvey.amazon.co.uk/csad/help/node/GKMQC26VQQMM8XSW
- Amazon older update sequencing: https://digprjsurvey.amazon.co.uk/csad/help/node/GX3VVAQS4DYDE5KE
- D01200 Kindle Touch Kiosk: https://github.com/bishopdynamics/kindle-touch-kiosk
- Apple Shortcuts API requests: https://support.apple.com/en-ke/guide/shortcuts/apd58d46713f/ios

### Competing display approaches

| Approach | Advantage | Risk/cost | Status |
|---|---|---|---|
| **A. Native frame fetch + display** | Small runtime and network footprint; ideal for static display | Requires validating framebuffer, filesystem, wake scheduling, touch input | **Preferred if feasible** |
| **B. Remote VNC client + hosted browser** | Documented D01200 precedent; possible touch forwarding | Always-on VNC host, network and rendering overhead, artifacts, security | **Fallback/experiment** |
| **C. Existing Kindle browser** | Potentially no native client installation | Outdated JS/TLS support, kiosk/refresh limitations | **Fallback only after tests** |

Do not choose an approach based solely on elegance. Require evidence of correct 600×800 output, repeatable refresh, reasonable system load, reconnect behaviour, and recoverability.

---

## 4. Product experience and pages

### Overall navigation

- Default landing page: **Today**.
- Five pages: **Today**, **Calendar**, **Shopping**, **Weather**, **Reading & News**.
- If touch works, tap left/right margins or bottom navigation hotspots to change page. Use large targets (at least 70×60 physical screen pixels where practical); avoid gesture-only interaction.
- If touch proves unreliable, automatically rotate pages by a configurable schedule, or show only Today with periodic changes.
- Refresh the *content* without arbitrarily resetting the currently selected page. On boot use Today unless a future setting explicitly remembers the selected page.
- One clear footer: page indicator + last data refresh/stale marker, compact enough not to dominate.
- No continuously animated elements. Clock shows the time of the most recent frame (five-minute increments), not a live ticking minute clock.

### Screen A — Today (home)

Priority order: 1) household/date, 2) time and temperature, 3) next two or three family events, 4) sunrise/sunset, 5) small daily thought, 6) subtle page/status footer. The home layout must remain readable even when events have long names; ellipsise safely and offer full details in the mobile Hub.

### Screen B — Family Calendar

Seven-day agenda with day headings, event time, concise event name and an all-day marker. Next week accessible through touch when possible. Make event privacy explicit: private items display **Busy** on the Kindle. Respect `Europe/London` time zone and British Summer Time transitions. Recurring events can be represented via occurrences produced by the backend. Distinguish cancelled, changed and all-day events.

### Screen C — Shopping

Readable checklist of open items, optionally grouped by category (Produce, Household, Other). Prioritise uncompleted items; cap visible item count and display `+N more` if needed. Changes are entered on phone. Completed items remain accessible in the Hub, but disappear from the Kindle by default. Avoid drawing interactive checkboxes unless tapping to complete is implemented and approved later.

### Screen D — Weather & Outdoors

Current condition, temperature, daily high/low, concise next six-hour forecast, rain likelihood, tomorrow and sunrise/sunset. Configure household location on the Hub; do not request device GPS. Weather can refresh every 15–30 minutes even though the Kindle checks for updates every five minutes. Cache upstream responses and show a stale label when necessary.

### Screen E — Reading & News

A short daily Bible verse or quotation with attribution/reference, plus three to five headlines and sources. Do not fetch/reproduce whole news articles. Use curated RSS sources configured in Family Hub. Bible translations must have a verified licence or be public domain; allow original household-authored quotes. Long quotes must truncate or switch to a quote-specific reading view without reducing text below readability minimums.

### E-ink visual rules

- 600×800 portrait frame; no dependence on external font installation on the Kindle (server renders fonts into pixels).
- Monochrome editorial style, e.g. black/near-black text on warm-looking white paper (actual pixel output grayscale).
- Typography: clear hierarchy, generous margins and high contrast. Validate at actual six-inch size, not just desktop zoom.
- Large numeric time; straightforward weather pictograms; avoid gradients, shadows and thin hairlines that dither poorly.
- Reserve predictable widget rectangles. A widget must not overflow or cover another widget.
- Export PNG for development preview; benchmark PNG vs other device-compatible frame formats at Kindle integration stage.
- Compare 1-bit dithered and 4-bit/16-level quantised images on real device for contrast and ghosting.
- Include light and dark-inverted themes only after real-world e-ink contrast tests; initial theme is white background/black text.
- Accessibility: no meaning encoded solely by colour, readable text, clear error/stale indicators.

---

## 5. Family Hub phone interface

Build a responsive web app with these routes or equivalent screens:

| Page | Core functionality |
|---|---|
| `/` | Household overview, next event, shopping count, Kindle state |
| `/shopping` | Add item, quantity, category; complete, undo, edit, delete; multiple lists architecture |
| `/calendar` | Add/edit/cancel family events, all-day and timezone, optional private flag, recurrence phase 2 |
| `/content` | Daily quote/verse input, attribution, rotation schedule, moderation/preview |
| `/news` | Enabled feeds, category/order, refresh and error state |
| `/display` | Page order, enabled widgets, selected location, update intervals, preview rendered screen |
| `/devices` | Device online/last check-in, frame version, current page, safe refresh request, diagnostics |
| `/family` | Invite members, roles and account management |

**Primary roles:** Owner/Admin (configuration and members), Editor (shopping/calendar/content), Viewer (read-only). Defaults can initially place the single household owner in Admin; design membership now even if invitations are delivered later.

### Editing expectations

- Changes save immediately when connected, with clear success/failure indicators.
- Phone forms are accessible and large enough for touch.
- Shopping items may be entered as free text without unnecessary setup.
- Quantity/unit fields optional; allow rapid repeated addition.
- Show last edited metadata inside Hub but do not display who added an item on Kindle unless enabled.
- Confirm destructive list-wide actions.
- Include lightweight empty states and validation messages.
- Support exporting family data as JSON/CSV, with owner authorisation.

### Calendar source strategy

**MVP authoritative source:** Family Hub's built-in event database. This guarantees functionality without an external provider.

**Future integration adapters:** read-only Google Calendar API, Microsoft Graph, published ICS feeds, and Apple/iCloud options when a secure officially supported method exists. Never require household members to share their iCloud password. Clarify whether imported events are editable in the original source; prevent double writes/duplication. Source-of-truth and conflict rules must be documented before enabling bidirectional sync.

---

## 6. iPhone Apple Shortcuts

Build API contracts and installation instructions for four shortcuts:

1. **Add Shopping Item**: ask for item, optional quantity/category/list; POST; present server acknowledgement.
2. **Add Family Event**: ask title, date, time, all-day flag; POST; confirm with formatted start time.
3. **Send Today's Thought**: share text or type a quote, optional attribution; POST to a review/scheduled queue; never automatically publish untrusted webpage content without confirmation.
4. **Request Display Refresh**: ask server to invalidate/render current frame; actual Kindle delivery happens on its next check unless touch/wake mechanisms support faster delivery.

Use the Apple Shortcuts **Get Contents of URL** action with HTTPS and JSON. Provide a written setup guide with screenshots placeholders or exact steps. Store per-device credentials in protected shortcut variables/configuration rather than URL query strings; recognise that shortcuts are exportable and credentials must be revocable. Create separate keys for each phone and permission scope (e.g. `shopping:write`, `calendar:write`, `content:submit`, `display:refresh`).

Server must support idempotency keys for retry-prone requests and return consistent JSON errors. Do not claim iCloud Reminders is directly integrated. Potential later option: Apple Reminders shortcut reads selected items locally and sends them to our API, with explicit duplicate/conflict rules.

---

## 7. Modular feature framework

Separate **data providers**, **widgets**, and **page layouts**:

- `DataProvider`: fetches external data or queries household storage; validates and normalises schema; has TTL, source metadata and stale/error policy.
- `Widget`: renders a typed data snapshot to a constrained rectangle; supplies minimum dimensions, font rules and empty/error states.
- `Page`: declares widget instances, bounds, ordering, visibility, fallback and navigation metadata.
- `DisplayProfile`: hardware dimensions, grayscale mode, image codec, refresh and touch capability.

### MVP modules

`clock`, `weather`, `sunrise-sunset`, `calendar`, `shopping`, `daily-content`, `news`.

Each module must have a documented contract including: input schema, output schema, permitted data, caching TTL, failure behaviour, unit tests and visual snapshot/golden-frame tests.

**Future additions** without rearchitecting: birthdays, household chores, school dates, countdowns, transport, home sensors/Home Assistant, photo cards, reading plans and a second screen/device. New modules require server-side registration and authorisation, not arbitrary remotely downloaded Kindle code.

### Rendering specification

- Input: typed `DisplaySnapshot` (`pageId`, `householdTimeZone`, `generatedAt`, widget data, selected layout, rendererVersion).
- Output: deterministic 600×800 grayscale frame with `frameId`, SHA-256 hash, render version and MIME type.
- The renderer must be a pure or mostly pure function of snapshot + fonts/assets (no live API calls during drawing).
- Font and layout assets ship with backend; use correctly licensed fonts and do not rely on system font variation between environments.
- Introduce a visual regression test suite with reference PNG images for empty, typical, overflow, offline and error states.
- Never allow upstream text to be treated as executable HTML or paths to local files.

---

## 8. Backend, API, database and scheduling

### Preferred stack (revise based on local environment discovery)

- TypeScript monorepo; Node.js LTS runtime supported by hosting provider.
- React + TypeScript for mobile Family Hub, with accessible components and modest dependency footprint.
- REST + JSON with schema validation (e.g. Zod or equivalent).
- Relational store, preferably MySQL if existing Hostinger environment works; SQLite permissible for local development and very small single-node deployments. Avoid maintaining two divergent SQL implementations without migration tests.
- Server-rendered frames using Sharp, SVG-to-image, Canvas or a similarly maintained rasterisation tool; confirm typography support, memory behaviour and deployment compatibility.
- Scheduled jobs for upstream weather/news/calendar fetches, stale-age detection and image invalidation. Avoid doing heavy provider fetches inside Kindle poll requests.
- Testing with unit, API integration, end-to-end mobile browser, image snapshot and failure-injection tests.

### Core entities

- `Household(id, name, timeZone, location, createdAt)`
- `Member(id, householdId, userId, role, status)`
- `ShoppingList(id, householdId, title, position)`
- `ShoppingItem(id, listId, title, quantity?, unit?, category?, completedAt?, version, updatedAt, createdBy)`
- `CalendarEvent(id, householdId, title, startAt, endAt, allDay, timeZone, visibility, status, source, sourceId?, recurrence?)`
- `DailyContent(id, householdId, type, text, attribution, sourceReference?, licence?, scheduledDate, status)`
- `NewsFeed(id, householdId, feedUrl, name, category, enabled, ttl)`
- `DisplayDevice(id, householdId, profile, activePage, lastCheckIn, status, revokedAt?)`
- `PageLayout(id, householdId, pageId, widgetConfig, order, enabled, version)`
- `ShortcutCredential(id, householdId, memberId, scopes, secretHash, expiresAt, revokedAt, lastUsedAt)`
- `Frame(id, displayId, pageId, contentHash, imagePath, generatedAt, expiresAt, rendererVersion)`
- `AuditEvent(id, actorId, householdId, action, entityId, createdAt)`

Use migrations, foreign keys, household scoping on every query, indexes for list/event/date lookups, UTC storage for instants and explicit timezone conversion at the boundary. Build concurrency handling (optimistic version or transaction) so two phones can edit items reliably. Do not log secrets or raw request bodies containing private content.

### API v1 — proposed, not existing

| Endpoint | Purpose | Authentication |
|---|---|---|
| `POST /api/v1/session/*` | Login/logout and session status | Session auth |
| `GET /api/v1/dashboard` | Mobile Hub summary | Household viewer+ |
| `GET /api/v1/shopping/lists` | Fetch lists | Household viewer+ |
| `POST /api/v1/shopping/lists/:id/items` | Add shopping item | Editor or scoped shortcut |
| `PATCH /api/v1/shopping/items/:id` | Edit/complete item | Editor |
| `GET /api/v1/calendar/events?from=&to=` | Family agenda | Viewer+ |
| `POST /api/v1/calendar/events` | Add event | Editor or scoped shortcut |
| `GET /api/v1/content/daily` | Daily thought | Viewer+ |
| `POST /api/v1/content` | Submit daily text | Editor or scoped shortcut |
| `GET /api/v1/news/feeds` | Manage/inspect sources | Viewer+ |
| `PUT /api/v1/display/:id/layout` | Change configuration | Admin |
| `POST /api/v1/display/:id/refresh` | Queue refresh | Admin or scoped shortcut |
| `GET /api/v1/display/:id/preview?page=` | Authenticated image preview | Viewer+ |
| `GET /display/v1/:id/manifest` | Restricted device manifest | Device-only bridge/client credential |
| `GET /display/v1/:id/frames/:frameId` | Restricted rendered image | Device-only bridge/client credential |
| `POST /api/v1/shortcuts/shopping` | Quick add | Scoped shortcut |
| `POST /api/v1/shortcuts/calendar` | Quick event | Scoped shortcut |
| `POST /api/v1/shortcuts/content` | Quick quote submission | Scoped shortcut |

Keep device endpoints **read-only**; any future `device input` path for page navigation should be authenticated, rate-limited and limited to a whitelist of page IDs. Device API response must not disclose household members' credentials or unpublished/private events.

### Refresh and caching logic

- Kindle checks the frame manifest **every 300 seconds** while awake/connected.
- Manifest contains monotonic `version` or content hash; client only downloads changed image.
- Clock is displayed at last render time, in five-minute increments, unless another interval is explicitly adopted after battery/ghosting testing.
- Shopping and calendar edits invalidate relevant page snapshots immediately on backend; changed frame becomes available at next poll.
- Weather source TTL: 15–30 minutes; news: 30–60 minutes; solar data: daily; daily verse: daily.
- Bound upstream retries, exponential backoff and provider-rate limits. Serve cached stale-but-useful information with explicit age indicators.
- For failures, keep last valid frame; do not replace with a blank screen. After reboot, show cached frame first.
- Distinguish `last source update`, `last frame render` and `last Kindle check-in` in monitoring.
- Implement `ETag`/hash comparison or equivalent and atomic frame writes so interrupted download never corrupts the active screen.
- Define partial/full refresh policy only after Kindle display-method tests; start conservatively and measure ghosting.

---

## 9. Security and privacy

### Threat model

Assets: family appointment titles/times, shopping history, email-like notifications if added later, service credentials, household accounts. Threats: unauthorised internet access, insecure legacy Kindle TLS, stolen/reused shortcut token, malicious RSS content, exposed Hostinger config, cross-household data leaks and access via a shared family device.

### Required controls

1. Browser/Shortcuts ⇄ backend use modern HTTPS with valid certificates; no insecure SSL bypasses.
2. Passwordless or password-based account authentication should follow established best practice; secure sessions (`HttpOnly`, `Secure`, appropriate `SameSite`), CSRF protection where applicable, rate limits and session revocation.
3. Explicit household tenancy enforced on server, never only by hidden frontend controls.
4. Store secrets in environment/secret manager; never commit `.env`, token files, or printed credentials.
5. Shortcut tokens per person/device, scope-minimised, expiry/rotation and revocation; avoid embedding tokens in URL strings.
6. RSS/web inputs must be parsed/sanitised as plain data; block SSRF, internal metadata URLs and dangerous redirects. Restrict image/resource fetches.
7. Keep no provider OAuth tokens or management credentials on the Kindle.
8. If a local HTTP bridge is required for legacy compatibility, **only render a pre-authorised, limited non-sensitive frame** on a restricted, firewalled LAN/VLAN; no editing API, no port forwarding and no unrestricted access to backend. Document residual risks and stop if isolation cannot be achieved.
9. Calendar `private` events become `Busy` (or are omitted) on all Kindle frames. Household admin can configure stricter display privacy.
10. Define backups, restore test, retention policy and account/data deletion path before production.
11. Version and log security-sensitive actions (login, member invites, credential creation/revocation, configuration changes). Avoid logging exact calendar or shopping content by default.
12. Protect public deployment through robust deployment configuration, origin checks and monitoring.

### Data visibility tiers

- **Public household screen:** date, weather, generic daily content, filtered calendar, shopping items intentionally selected for display. Assume visitors may see the screen.
- **Authenticated Family Hub:** full household list/calendar data consistent with role.
- **Backend only:** secrets, provider tokens, audit/logging details and member authentication data.

---

## 10. Power and hardware operational safety

The unit is ~15 years old; leaving it charging continuously is a **hardware safety decision**, not just a software setting.

- Inspect for battery swelling, excessive heat, unexpected resets, damaged cable/port and unstable charging **before** unattended operation.
- Never bypass the battery controller or replace the battery with arbitrary resistors or power wiring.
- Keep the original battery management path unless a qualified repair is explicitly approved.
- Treat temperature telemetry as optional; do not invent availability of a battery-temperature sensor.
- Prefer static frames, low CPU/network activity and reduced needless full refresh cycles.
- If battery condition is uncertain or unsafe, stop deployment until battery is assessed/replaced properly.
- A scheduled external charging switch may be evaluated later but must not be assumed safe or sufficient without testing.
- Test reconnect after power loss and battery depletion, and inspect restart/boot behaviour.

---

## 11. Development workflow and repository structure

Suggested monorepo:

```text
kindle-family-display/
├── apps/
│   ├── family-hub-web/        # mobile web UI
│   └── kindle-client/         # gated; no device changes initially
├── services/
│   ├── family-api/            # REST, auth, household logic
│   ├── frame-renderer/        # 600x800 images and layouts
│   ├── data-sync/             # weather, solar, news, later calendar adapters
│   └── kindle-bridge/         # optional, gate before real use
├── packages/
│   ├── contracts/             # shared schemas and DTOs
│   ├── widget-core/           # page composition and widget interfaces
│   ├── widget-modules/        # clock, weather, calendar, shopping, etc.
│   ├── design-tokens/         # type, spacing, grayscale
│   └── test-fixtures/         # safe fake household content
├── shortcuts/                # instructions/templates, no live credentials
├── docs/
│   ├── architecture/
│   ├── device-audit/
│   ├── security/
│   ├── design/
│   ├── adr/                   # architecture decision records
│   ├── runbooks/
│   └── acceptance/
├── infra/                    # local compose / deployment manifests
├── scripts/
├── .env.example
├── README.md
└── MASTER_PLAN.md
```

Engineering conventions:

- Monorepo scripts: `lint`, `typecheck`, `test`, `test:integration`, `test:e2e`, `build`, `dev`, `render:preview` (names can vary if documented).
- Pinned lockfile and Node LTS; migrations and repeatable seed fixtures.
- `.env.example` only contains names and fake placeholder values.
- Unit tests for domain logic; integration tests for API/database; browser tests on mobile viewport; renderer golden-frame images.
- Maintain `docs/decisions.md` or ADRs and `docs/progress.md` with stage acceptance and blocker notes.
- Every change in its own reviewable commit; no silent production modification.

---

## 12. Milestones and authorisation gates

**Meaning of gates:** PASS = proceed; FAIL = fallback/stop; UNKNOWN = do not assume. Each milestone requires evidence in a named Markdown report and test output. The user has authorised planning and safe local development of the platform, **not physical Kindle modification or production deployment**.

### M0 — Read-only hardware feasibility (parallel with safe local development)

- [ ] Record exact model and firmware as seen on device.
- [ ] Document USB storage access and backup inventory (without overwriting).
- [ ] Record battery safety observations and screen/touch/Wi-Fi behaviour.
- [ ] Review jailbreak compatibility and recovery material for *that exact firmware*.
- [ ] Compare native-image, VNC and browser designs; list unresolved tests.
- [ ] Write `docs/device-audit/M0-report.md` with references, risks and go/no-go recommendation.

**Gate G0:** No firmware/root/install operation before exact unit, safety, and user authorisation are documented.

### M1 — Architecture and development environment

- [ ] Inspect existing repo/workspace; no overwrite of unrelated work.
- [ ] Document architecture decisions, exact runtime, hosting constraints and selected database.
- [ ] Scaffold monorepo, formatter/linter, test runner, README and local environment.
- [ ] Provide local dev instructions and a mock-mode startup path.

**Gate G1:** Clean install, typecheck, lint, tests and local mock startup repeatably pass.

### M2 — Typed domain + core APIs

- [ ] Define schemas, migrations, household scoping, auth/session model and roles.
- [ ] Implement shopping list operations, calendar CRUD, daily-content input and display configuration.
- [ ] Add idempotent shortcut write endpoints and audit boundaries.
- [ ] Seed fake test data only.

**Gate G2:** API contract tests, authorisation/tenant-isolation tests, concurrency and invalid-input tests pass.

### M3 — Family Hub mobile web application

- [ ] Implement responsive phone interface, shopping, calendar, daily-content, display settings and device status.
- [ ] Clear empty/error/loading/offline states.
- [ ] Test common iPhone Safari viewport widths and keyboard navigation.

**Gate G3:** Household member can add/check shopping items, enter events and preview data on a phone-like viewport, with correct permissions.

### M4 — Modular data adapters + scheduler

- [ ] Weather/solar adapter with location, unit/timezone handling and TTL.
- [ ] Curated RSS adapter with output sanitisation and SSRF safety.
- [ ] Daily quote / licensed Bible verse content rules and scheduling.
- [ ] External calendar interface stub; do not require provider credentials for MVP.

**Gate G4:** Tests for cache expiration, external API failures, wrong RSS format, stale data, timezone/DST and content licensing fields.

### M5 — E-ink renderer + desktop simulator

- [ ] Build all five pages at 600×800 with deterministic test fixtures.
- [ ] Widget registry and per-page configuration; overflow-safe typography and fallbacks.
- [ ] Render PNG previews, frame manifests, hashes and cache control.
- [ ] Add simulator to switch screens/toggle mocked failures without a physical Kindle.

**Gate G5:** Golden image tests pass; visual review at physical-scale mockup; 600×800 output exact; no critical clipping; changed content changes hash; unchanged content does not.

### M6 — Apple Shortcuts and multi-user readiness

- [ ] Document and test HTTP JSON operations for quick-add and event creation.
- [ ] Implement per-device scoped credential rotation and revoked-token tests.
- [ ] Prepare step-by-step iPhone Shortcut build instructions.
- [ ] Test duplicate delivery/idempotency and offline retry handling.

**Gate G6:** Two separate simulated devices cannot use each other's revoked credentials; submitted items appear in Hub and rendered preview.

### M7 — Kindle integration research and controlled prototype **(explicit separate approval required)**

- [ ] Select real-client approach based on G0 and available recovery plan.
- [ ] Obtain explicit user approval **before** jailbreak/firmware/install commands.
- [ ] Verify package provenance/checksums and backup/recovery.
- [ ] Test image transfer, touch events, refresh cycles, system resources and restart.
- [ ] If necessary, isolate Kindle via a local bridge with no upstream secrets.

**Gate G7:** Repeated frame delivery works without exposing backend credentials, and the device can recover from failures. If not, use automatic-display or alternate-device fallback.

### M8 — Deployment and operational acceptance **(explicit approval required)**

- [ ] Confirm actual Hostinger plan can run chosen services, worker/scheduler and image-rendering dependencies.
- [ ] Verify TLS, DNS, backups, secrets, monitoring, rate limits and restore runbook.
- [ ] Run 72-hour soak test, Wi-Fi interruption/reconnect, empty screen protection, repeated touch and rendering tests.
- [ ] Validate charging safety and device temperature behaviour.
- [ ] Review household privacy and data-retention policy.

**Gate G8:** User approves production deployment after functional/security/hardware checks.

---

## 13. Acceptance tests (release-level)

| Test | Required evidence |
|---|---|
| Renders five pages | 600×800 golden frames without overflows |
| Five-minute checks | Manifest polling at nominal 300s; changes appear within next successful poll while awake/network available |
| Avoids unnecessary redraws | Identical content hash skips image transfer/refesh |
| Weather / sun | Correct location, timezone, high/low, sunrise/sunset; stale graceful fallback |
| Calendar | All-day events, timezones, DST, privacy flags, event ordering |
| Shopping | Two phone users can add/complete without lost updates; clear undo |
| News/quotes | Sanitised headlines, cited sources, license-aware verse/quote storage |
| Shortcuts | Authenticated quick-add; success/error returned; duplicate retry idempotent |
| Offline | Last valid frame survives outages; no false assertion of freshness |
| Touch | Changes pages reliably if G7 passes; automatic-only mode otherwise |
| Security | Tenant isolation; no secrets on device; scoped and revocable tokens; no open edit API |
| Battery/device | No unsafe operation, repeated boot/reconnect; no unattended charging with suspect battery |
| Reliability | 72-hour sustained test after real-device integration |
| Restore | Database restore and Kindle recovery/runbook tested before release |

### Performance budgets (targets, not promised hardware facts)

- Backend image render for one page: initially target <2 seconds on hosting hardware; benchmark and refine.
- Poll manifest: small payload (ideally <2 KB excluding network overhead).
- Resulting full frame: compress and benchmark; no fixed byte guarantee before representative screens.
- Phone Hub common interactions: visible response target <200 ms locally, network acknowledgement separate.
- Clock: nominal 5-minute visible updates, **not** precise minute-by-minute accuracy.
- Kindle processing: no full-page web rendering if native frame client passes; keep memory footprint minimal.

---

## 14. Critical open questions and default decisions

| Open item | Provisional default | Resolution point |
|---|---|---|
| Kindle current firmware | Unknown; do not update | M0 |
| Kindle battery condition | Unknown; do not leave plugged unattended until checked | M0 |
| Native frame rendering feasibility | Preferred but unproven | M0/G7 |
| Household calendar provider | Family Hub internal calendar | M2; external adapters later |
| Household location | Configurable by admin; no hardcoded street address | M3/M4 |
| News sources | Opt-in curated RSS, no defaults presenting editorial bias | M4 |
| Bible translation/licence | Public-domain or clearly licensed text | M4 |
| Hosting topology | Cloud Family Hub, optional restricted home bridge | M1/G7 |
| Always-on computer at home | Unknown; do not assume availability | M1/G7 |
| Accounts/membership | One admin initially; future invitations designed in | M2/M3 |
| Family privacy threshold | Hide private events on Kindle | M2 |
| Refresh outside waking hours | Five-minute checks while awake; power behaviour to test | M0/G7 |

Avoid blocking independent software work on these unknowns. Record them as explicit assumptions and stubs where necessary.

---

## 15. Instructions for Claude Code to start immediately

### First response to user / first actions

1. Read this whole document and summarise your interpretation in 8–12 sentences.
2. Inspect the local working directory and toolchain **read-only**, noting whether an existing repository exists; never overwrite an existing project automatically.
3. Create or update a stage tracker indicating M0–M8 status, assumptions and the next approved task.
4. Begin **M1 safe local scaffolding**, followed by **M2–M5 iterative application work** with fake household data, unless the user directs a different order. Hardware audit M0 may be documented but must not require modifying the Kindle.
5. Ask for secrets or account connection only when an integration actually requires them; use mocks until then. Do not ask the user for the firmware to proceed with server/frontend development.
6. After each milestone, report files changed, tests run/results, screenshots/frame previews when relevant, remaining risks and whether an approval gate was reached.
7. Before performing any irreversible action, write the proposed command and its consequences and **request explicit approval**.

### First implementation batch (approved scope)

- Set up repository, tooling, docs and clean `README`.
- Implement mocked domain entities and shared validation schemas.
- Build a minimal Family Hub shell, shopping-list CRUD and internal calendar entry form.
- Build an initial server-side 600×800 **Today** frame with safe sample data and a browser preview page.
- Write tests for schema validation, first shopping workflows and exact frame dimensions.
- Stop and summarise milestone state; do not attempt Kindle integration in this batch.

### Important prohibitions

**Do not:** jailbreak; run `fastboot flash`, recovery-install commands, Kindle update packages, root commands, or arbitrary third-party scripts; change device boot mode; wipe data; edit production databases; change public DNS; publish secrets; disable HTTPS certificate validation; expose a legacy HTTP service to the public internet; silently buy equipment; or claim that a test was performed on physical hardware when it was simulated.

### Definition of first successful demo

A local website on the Mac can log into a test household, add an item to a shopping list, add a family event, select the Today page, and display a correct 600×800 monochrome PNG with that information. A documented fake Shortcut HTTP request adds another item, and a subsequent render reflects the change. **No Kindle connection is necessary for this first demo.**

---

## 16. Suggested initial Claude Code prompt

Copy/paste alongside this document (or point Claude Code at `MASTER_PLAN.md`):

> You are the lead engineer for the **Kindle Family Display** project. Read `MASTER_PLAN.md` in full and treat it as the authoritative product brief. I authorise **local software development only**: repository setup, typed backend, mobile Family Hub, shopping/calendar modules, mock data, 600×800 e-ink renderer, browser preview, tests and documentation. First inspect my repository and environment. Create an implementation checklist and execute the first safe batch through a working local demonstration. Keep the design modular and lightweight. Use the exact milestone and security gates in the plan. Do not change the physical Kindle, jailbreak, update firmware, flash, install packages on it, deploy publicly, or touch production services. If something is unknown, select a documented, reversible default and continue with safe local work. At the end, give me a concise progress report, actual test results, how to run the demo, and what needs my approval next.

---

## 17. Future release opportunities (not MVP)

- Integrate a shared Google/Microsoft calendar (read-only initially).
- Offer local Apple Reminders → Family Hub Shortcut import with explicit conflict rules.
- Build tap-to-complete shopping on Kindle if input latency and network security permit.
- Household chores, birthdays, anniversaries, prayer/reading plan and school calendar.
- Weather warning indicators and indoor temperature integration via sensors.
- Additional e-ink/tablet display profiles using the same renderer and family data.
- Smart page rotation by time of day or content priority.
- Render a QR code for opening the relevant Family Hub page, without embedding private session tokens in the code.

**End of master plan.**
