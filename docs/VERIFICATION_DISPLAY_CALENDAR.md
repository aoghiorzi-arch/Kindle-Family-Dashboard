# Display review and recurring calendars — verification

Date: 28 October 2026. Base: merged PR #3, `57fa918644aff76ac9ca64c968853b0a7a3b9b7e`.

## Scope and behaviour

This batch groups the next two roadmap items: review/fix the Today layout and make calendars useful without repeated manual imports.

The display now handles long dates, weather, unbroken words, attribution and shopping text, and shows an additional-event count. `python3 -m app.review` generates four fictional, self-contained printable review pages. See `DISPLAY_REVIEW.md` for findings and the remaining user paper acceptance step.

Calendar parsing now uses pinned `icalendar==7.3.0` and `recurring-ical-events==3.8.2`. Daily, weekly, monthly and yearly series support counts/end dates, weekdays/intervals, exclusions/additional dates and moved/cancelled instances. Floating/unknown-TZID values use the household zone. Private series remain private when an exception omits CLASS. Occurrences are expanded for a rolling 31 days; singleton events retain their dates. Only occurrence start dates reach the Today screen; multi-day occupancy across all days is outside this implementation.

Each parse runs in a subprocess with a six-second wall-clock limit, 500 component/occurrence cap, 2 MB input cap, and Unix memory/CPU limits (512 MiB/five seconds). Subdaily rules are skipped and their count is shown to admins. Invalid sources or failed/oversized expansion preserve the previous import/feed data. Sources are retained privately in SQLite and re-expanded locally after each date change, so saved series can continue while a feed is offline.

Admins can enable/pause automatic refresh for each feed. Existing and new feeds default to manual. The schedule and last attempt persist across restart; retries are limited to once per 30 minutes. Downloads run in a separate calendar thread, use the existing pinned-public-address HTTPS path and retain the no-redirect/2 MB protections, with a deadline during downloading. DNS uses the operating system resolver. Pausing prevents future downloads; an in-flight request may finish. CLI and server processes should not be scheduled as duplicate feed workers.

Atomic source updates prevent a completed download/projection from recreating a deleted source, overwriting a newer import, or publishing against a changed feed time zone. Last-good events survive download/parse failures. Feed addresses/source text are still unencrypted local data and need protection before deployment.

## Validation

The existing 97-test suite passed after the first implementation. Added coverage checks recurrence/DST, extra/excluded dates, moved/cancelled/private instances, rolling-window and resource limits, source retention while offline, scheduled retries/restarts, migrated manual defaults, source deletion/replacement races, admin/CSRF/household permissions, downloader limits/redirect/DNS protections, private-address error handling, and screen text bounds/physical dimensions.

The real phone browser workflow now also imports recurrence and enables, persists and pauses a feed schedule, including a phone-width overflow check. Tests use fictional calendar/weather data and injected feed downloaders, never real provider accounts.

Final command (same local browser override as the previous milestone):

```bash
E2E_CHROMIUM_EXECUTABLE_PATH=/path/to/chrome-headless-shell \
  python3 -m unittest discover -s tests -v
```

Actual final result:

```text
Ran 124 tests in 61.036s

OK
```

No tests were skipped; all three Playwright workflows passed. Runtime: Python 3.12.14, Pillow 12.3.0, Node 24.22.1, Playwright 1.62.1 and Chrome for Testing headless shell 134.0.6998.35. Python compilation, JavaScript syntax and `git diff --check` passed. The printable HTML was also opened in Chromium with print media enabled: all four images loaded at 600×800, each with a CSS print box of approximately 344.906 × 459.875 pixels (91.257 × 121.677 mm at 96 CSS pixels/inch). This confirms the browser print layout, not a physical paper/E Ink acceptance.

## Remaining gates

User paper readability acceptance, physical hardware audit/integration, encryption of private feed/source storage, Shortcut retry/idempotency, backups/restore, broader concurrency, live weather, production security/hosting and the 72-hour soak remain outstanding. This batch performs local software work only; it does not connect or modify the Kindle or deploy a public service.

Primary API references: [recurring-ical-events API](https://recurring-ical-events.readthedocs.io/en/v3.8.0/reference/api.html), [icalendar event API](https://icalendar.readthedocs.io/en/stable/reference/api/icalendar.cal.event.html). The installed pinned versions' behaviour is covered by the tests above.
