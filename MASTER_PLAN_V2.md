# Kindle Family Display — Lean Execution Plan (v2)

**Date:** 28 October 2026  
**Status:** Safe local software prototype started. **No authority** to modify Kindle firmware, install device-side software, connect to the physical device, deploy publicly or access production accounts.  
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

## Current prototype status (this delivery)
- Local Python/Pillow renderer, editable local mock web page, sample fixtures and unit tests.
- **Not included:** persistent DB, authentication, external weather/calendar integrations, device bridge, hardware assessment, Kindle touch support, real-time polling, production hosting.
- Changes in local demo reset on server restart, by design.

## Next explicitly safe task
Refine Today layout based on a 6-inch print/physical-size review; then implement the authenticated persistent Family Hub locally. Run the read-only Kindle audit in parallel. Seek separate permission before any physical device changes.
