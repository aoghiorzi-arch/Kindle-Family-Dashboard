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
| M2 — Domain/APIs | Validation, persistence, household isolation, sessions, roles, shopping/events; concurrent retries/revocation and snapshot writes tested | Broader audit requirements remain. G2 is partial. |
| M3 — Family Hub | Mobile shopping/calendar/settings and authenticated preview; browser workflows tested | Safari/accessibility review, broader offline states and additional display settings remain. G3 evidence covers the lean flow. |
| M4 — Data/scheduling | Fake weather TTL/failure cache, computed sunset, daily verse, local frame worker, recurring calendars, opt-in feed scheduling and encrypted feed/source storage | Live weather and RSS remain deferred. G4 is partial. |
| M5 — Renderer/simulator | Deterministic 600×800 Today PNG, privacy masking, atomic files, hashes, persisted fallback | Printable physical-size fixtures and bounds checks are implemented; user paper acceptance, golden-image suite and later pages remain. G5 is partial. |
| M6 — Shortcuts/multi-user | Scoped/revocable tokens, permissions/isolation, persistent retry receipts and transactional authorization; concurrency/restart/deletion/rollback covered | Client offline queue and full device credential scenarios remain. G6 is partial. |
| M7 — Kindle integration | No device changes or client implementation | Requires completed hardware assessment and separate explicit approval. |
| M8 — Deployment/acceptance | Local-only; encrypted calendar fields, verified manual snapshots, fixture recovery/login/frame drill and credential reset | Actual-machine custody/recovery, off-machine retention, key rotation, HTTPS/hardened hosting, 72-hour soak and production approval remain. |

## Next priorities

1. Print and review the generated Today fixtures at physical six-inch size; automated overflow/privacy checks and visual inspection are complete.
2. Establish actual-machine key/backup custody and rehearse recovery; local snapshot/restore, field encryption and credential reset are implemented.
3. Complete Safari/accessibility, clean-install CI, remaining audit requirements and the soak test; concurrency/revocation and snapshot consistency are covered locally.
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

## Third software batch — calendar storage protection

- [x] Encrypt feed addresses and cached calendar sources using authenticated, row/household-bound encryption.
- [x] Generate a separate owner-only key; support an external key path and reject lost/wrong/unsafe keys without reset.
- [x] Migrate legacy plaintext fields transactionally, retain event IDs/settings, and clean SQLite logical files before serving requests.
- [x] Retain last-good events on storage errors; return a fixed HTTP 503 without exposing secrets.
- [x] Test ciphertext tampering/substitution, migration rollback/cleanup recovery, WAL conversion, restart and database/key copy recovery.
- [ ] Backup scheduling, rotation tooling and broader deployment hardening remain open.

See `CALENDAR_STORAGE.md` and `VERIFICATION_CALENDAR_STORAGE.md`. This supersedes plaintext feed/source warnings in earlier verification reports. Derived events, household records and frames remain sensitive unencrypted data.

## Fourth software batch — recovery and Shortcut retries

- [x] Consistent SQLite backup, including WAL, with integrity, foreign-key and encrypted-field verification.
- [x] Restore to a new private directory using the separate matching key; refuse overwrite and clear browser sessions.
- [x] Preserve calendars and regenerate frames on demand; recovery now revokes restored API tokens, clears receipts and pauses feeds as documented in the follow-up below.
- [x] Persistent token-scoped request IDs, atomic shopping insertion/receipt, conflict responses and concurrent retry tests.
- [x] Document recovery rehearsal and UUID reuse in Shortcuts.

See `BACKUP_RESTORE.md`, `SHORTCUTS.md` and `VERIFICATION_RECOVERY.md`. Backup scheduling and full-database encryption remain outside this batch.

## Recovery and concurrency hardening follow-up

- [x] Add explicit read-only snapshot verification, schema checks and bounded copy/verification work.
- [x] Reset recovered credentials/receipts and pause automatic feeds; verify offline recurrence, fresh frames and password login.
- [x] Check token identity, current scope and revocation inside the shopping transaction, including unkeyed requests.
- [x] Bound saved requests per token while allowing matching retries at capacity.
- [x] Exercise concurrent WAL snapshots, eight-way same/distinct-ID writes, stale authorization, revocation ordering, rollback, restart, CLI and failure paths.

Evidence and remaining limits: `VERIFICATION_RECOVERY_HARDENING.md`. Existing `request_id` and directory-based backup commands remain compatible.

## Stage A — prepare without the Kindle (branch `stage-a-kindle-prep`)

- [x] A1 Display token (`display:read`), `/api/display/frame.png`, 304s, revocation, household scoping, restore invalidation — `tests/test_display_token.py`.
- [x] A2 `scripts/kfd`, `/healthz`, pinned dependencies, clean-clone install and `scripts/kfd smoke` passed (Linux, Python 3.13). macOS and the user's actual OS unverified.
- [x] A3 Loopback-only enforcement, `KFD_PUBLIC_ORIGIN` mode (Secure cookies, HSTS, exact Origin/Host), proxy and firewall guidance — `tests/test_network_boundary.py`. Real TLS proxy, phone CA trust and Kindle TLS compatibility are **not** verified.
- [x] A4 `display_client/` (bounded download, PNG/CRC validation, atomic cache, ETag, backoff, no redirects, token from 0600 file) — `tests/test_display_client.py`. Unverified on hardware.
- [x] A5 `docs/HANDOVER.md`.
- Full suite: 214 tests pass. Fixed a pre-existing start-up race in one frame test and made `shutdown()` wait for workers.

State: ready for supervised Kindle connection, not "Kindle ready".
