# Kindle Family Display — Lean Execution Plan (v2)

**Date:** 28 October 2026
**Status:** Persistent local Family Hub implemented; automatic frame lifecycle added. Verification evidence and remaining work: [`docs/PROGRESS.md`](docs/PROGRESS.md). **No authority** to modify Kindle firmware, install device-side software, connect to the physical device, deploy publicly or access production accounts.
**Original specification:** [`docs/ORIGINAL_MASTER_PLAN.md`](docs/ORIGINAL_MASTER_PLAN.md) remains the product requirements/reference. Where these plans differ in *execution order or scope*, this v2 is the proposed working roadmap; it does **not** weaken the original security, hardware-safety or approval gates.

## Product goal
A beautiful, low-maintenance household appliance built around a 600×800 portrait Kindle Touch (D01200), showing useful family information without demanding attention. Phone-first edits; server-rendered monochrome screens; five-minute *checks* while connected, but image redraws only when meaningful content changes. Other display hardware remains a fallback.

## MVP cut
1. **Today**: date, up to three family events, weather/sunset, shopping count and a short thought. No live minute-by-minute clock in the first design. Start with 15–30 minute clock updates only if a visible time readout proves worthwhile.
2. **Family Hub**: simple mobile Today/Shopping/Calendar views and a separate Settings area. Single household with the architecture able to grow.
3. **Calendar**: manual entries work first; evaluate opt-in read-only ICS subscription early, protecting private feed URLs. Provider OAuth and bidirectional sync deferred.
4. **Weather**: server-only fetched/cached adapter; weather updates 15–30 minutes, with staleness indicated. Demo uses fake data only.
5. **Shortcuts**: shopping quick-add first; scoped, revocable credentials required before real deployment.
6. **Later**: separate Weather/Reading/News pages, configurable widget editor, broader multi-household system, full integrations and Kindle shopping edits.

## Working architecture
A **single backend app** containing internal domain, HTTP API, scheduler, data adapters and deterministic frame renderer. Avoid premature microservices. Store frames atomically with content hashes and retain the last verified frame. Keep provider secrets and family edit permissions off the Kindle. Production requires secure sessions, explicit household scoping, CSRF/rate limiting, backups and restore verification. Do not expose this unauthenticated local demo over a network.

## Sequence & gates

### P1 — Screen proof + read-only audit (approved local software work)
- Design and render attractive, contrast-safe 600×800 Today PNG with fake data.
- Provide browser preview and simple local forms to add shopping entries/events.
- Unit tests: exact dimensions, deterministic output, changed inputs change output, private event titles do not appear.
- Device **read-only** audit checklist: exact model/firmware, battery/charging condition, screen/touch, USB storage, Wi-Fi, reversible recovery research. Do not carry out any connected-device operation without the user's presence and understanding.
- **Exit:** demonstrable frame + test results + documented unresolved hardware risks.

### P2 — Controlled hardware proof (requires fresh explicit device approval)
- Choose candidate native frame delivery or VNC/browser fallback based on verified firmware and recovery route.
- First prove a single frame, then repeat refresh, resume/reconnect and, optionally, touch. Measure ghosting, temperature/power and failure recovery.
- **Stop:** if unsafe battery, unsupported recovery or unacceptable security compromises. **Never** treat approval of this plan as permission to jailbreak or modify the Kindle.

### P3 — Useful family application (local software work, then deployment approval)
- Shopping CRUD, simple calendar, cached weather/solar, daily content, basic admin settings.
- Introduce persistence, authentication, roles, validation, multi-user concurrency, safe private-event display and audit boundaries **before** family information or public hosting.
- **Exit:** phone edit updates rendered preview; end-to-end tests pass.

### P4 — Daily usability
- Shortcuts with scoped credentials, carefully secured optional read-only ICS import, refined mobile interface and extra pages only if validated by actual use.
- **Exit:** genuine household tasks can be completed quickly and reliably.

### P5 — Reliability + launch (requires explicit production approval)
- Validate chosen Hostinger plan or alternative runtime, credentials, HTTPS, jobs, backups/restore, device access controls, and 72-hour soak test.
- Last-known-good local frame, stale data state, protected private events, hardware charging safety.
- **Exit:** user signs off production/security/hardware checklists.

### P6 — Enhancement
Birthdays, chores, school dates, smart layouts and second display support, based on usage.

## Acceptance priorities
- The Today screen works well *without any interaction*.
- A 600×800 PNG renders with readable text at physical scale; no clipping.
- Editing an item on the phone changes the next frame; offline means old frame stays, never blank.
- Device has no editable endpoints or secrets.
- Stale data is distinguished from offline connectivity.
- Original document's consent rules, no-public-deployment rule, battery precautions, licensing requirements and tests remain mandatory.

## Current implementation status — 28 October 2026
- SQLite persistence, password sign-in, household isolation, admin/member roles, CSRF protection and local mobile editing are implemented.
- Shopping add/check/remove, manual events, private-event masking, calendar paste import and protected HTTPS feed retrieval are implemented. Daily/weekly/monthly/yearly recurrence, opt-in scheduled feed refresh and encrypted feed/source storage with a separate key are implemented.
- Sunset calculation, cached fake weather, daily verses, household settings and scoped/revocable shopping Shortcuts tokens are implemented.
- Today renderer produces a deterministic 600×800 PNG. A local background worker checks each household every minute, including date/event/verse/sunset rollover and weather TTL refresh. No browser or edits are needed for these checks while the server runs.
- Verified PNGs are published atomically beside the database, with content hashes. Unchanged images are not rewritten. Render/publication failures preserve the last valid household image across restarts.
- Authenticated browser previews check every minute while visible and on reconnect/return to the tab. Unchanged hashes receive 304 responses; failed updates keep the displayed image. Draft form values are preserved.
- No live weather provider, full-database encryption, key rotation tooling, scheduled backups, Kindle bridge, HTTPS or production hosting is included.
- Original M0–M8 gates remain in force. This is a partial implementation of the broader product, not a declaration that every original milestone has passed.

## Next work
1. Print the generated physical-size review sheet and record user readability acceptance; automated layout review and overflow fixes are complete.
2. Review key rotation, backup scheduling and deployment security. Verified backup/restore commands preserve separate key custody. Feed addresses and cached sources now use authenticated encryption; other household fields and frames still need protection.
3. Broaden multi-user concurrency and soak testing. Shortcut request IDs now prevent duplicate retry additions.
4. Complete the user-led hardware audit. Obtain separate explicit approval before device connection/modification or production deployment.

See [`docs/PROGRESS.md`](docs/PROGRESS.md) for the current checklist and [`docs/VERIFICATION_2026-10-28.md`](docs/VERIFICATION_2026-10-28.md) for this software milestone's evidence.
