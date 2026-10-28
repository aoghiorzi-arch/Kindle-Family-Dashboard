# Kindle Family Display — implementation checklist

Updated: 28 October 2026. Scope: local software, fictional data. The original product brief remains in `ORIGINAL_MASTER_PLAN.md`; `MASTER_PLAN_V2.md` defines the lean execution order. Hardware and production approvals have not been granted.

## This software milestone

- [x] Inspect current main (`527021ed1f80fa97b9579ca8d6db594ba1444887`), branches and open work. No open issues or pull requests at inspection.
- [x] Establish a Python/HTTP test baseline and resolve the local browser-runner dependency.
- [x] Verify persisted shopping data and existing sessions across a server restart.
- [x] Verify phone shopping/calendar editing and private-event masking through real browser pages.
- [x] Update README and roadmap to reflect the persistent, authenticated application already implemented.
- [x] Generate frames automatically while the local server runs, without an editor/browser request.
- [x] Check household-time-zone midnight rollover, imported events, daily content and weather TTL refresh.
- [x] Publish verified PNGs atomically, preserve unchanged hashes/files and retain the last good frame across failure/restart.
- [x] Poll visible previews without erasing form drafts; keep the old image on failure and clear it on sign-out.
- [x] Document remaining work and evidence in `VERIFICATION_2026-10-28.md`.

## Original milestone coverage

| Milestone | Current coverage | Remaining work / gate |
|---|---|---|
| M0 — Hardware feasibility | Checklist exists; device not assessed here | Exact firmware, battery, recovery research and user-led observations. G0 remains unknown. |
| M1 — Architecture/environment | Single Python backend, SQLite, bundled fonts, local startup, Python/HTTP/browser checks | Formal lint/type checks and repeatable clean-install CI are not established. G1 is partial. |
| M2 — Domain/APIs | Validation, persistence, household isolation, sessions, roles, shopping/events | Broader concurrency coverage, idempotent retries and audit requirements remain. G2 is partial. |
| M3 — Family Hub | Mobile shopping/calendar/settings and authenticated preview; browser workflows tested | Safari/accessibility review, broader offline states and additional display settings remain. G3 evidence covers the lean flow. |
| M4 — Data/scheduling | Fake weather TTL/failure cache, computed sunset, daily verse, local frame worker, recurring calendars and opt-in feed scheduling | Live weather and RSS remain deferred; source-secret protection remains. G4 is partial. |
| M5 — Renderer/simulator | Deterministic 600×800 Today PNG, privacy masking, atomic files, hashes, persisted fallback | Printable physical-size fixtures and bounds checks are implemented; user paper acceptance, golden-image suite and later pages remain. G5 is partial. |
| M6 — Shortcuts/multi-user | Scoped/revocable shopping tokens, permissions and isolation checks | Idempotency, duplicate/offline retries and full device credential scenarios remain. G6 is partial. |
| M7 — Kindle integration | No device changes or client implementation | Requires completed hardware assessment and separate explicit approval. |
| M8 — Deployment/acceptance | Local-only application | HTTPS, hardened hosting, protected feed secrets, backup/restore, 72-hour soak and production approval remain. |

## Next priorities

1. Print and review the generated Today fixtures at physical six-inch size; automated overflow/privacy checks and visual inspection are complete.
2. Recurrence and opt-in scheduled feed refresh are implemented; complete protection of stored feed/source secrets before deployment.
3. Protect stored private feed addresses, then verify backup/restore and Shortcut retry/idempotency.
4. Select a hosting/runtime approach after requirements are verified. No public deployment in this milestone.
5. Complete the hardware checklist with the user before selecting or installing any Kindle-side component.

The app must be running for periodic checks. While stopped, its saved image remains on disk; browser polling resumes when connectivity returns. This work does not establish a physical-device offline cache or power behaviour.

## Second software batch — display review and calendars

- [x] Fit long dates, weather, quotes and attributions within the 600×800 layout; show event overflow and clear empty states.
- [x] Add a self-contained printable physical-size review sheet with a 50 mm calibration line and four fictional scenarios.
- [x] Add bounded daily/weekly/monthly/yearly recurrence, exclusions, extra dates and moved/cancelled instances.
- [x] Retain source imports and extend their rolling window locally after date changes, including while offline.
- [x] Add persisted, admin-only, opt-in automatic refresh; default migrated/new feeds to manual and preserve last-good events on failures.
- [x] Verify SSRF controls, transport deadlines, calendar limits, recurrence privacy, concurrency with source deletion/replacement, permissions and browser controls.
- [ ] User paper readability acceptance; physical Kindle audit and production/hardware gates remain open.

See `DISPLAY_REVIEW.md` and `VERIFICATION_DISPLAY_CALENDAR.md` for evidence and limits. This supersedes the recurrence/scheduling outstanding items in the earlier verification report.
