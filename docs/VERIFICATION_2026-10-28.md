# Local Family Hub verification — 28 October 2026

## Outcome

The persistent Family Hub is verified locally, and the display now updates without a phone edit. A background worker derives each household's current date, imported events, daily verse, sunset and cached weather every minute while the server runs. Authenticated previews poll independently of forms and preserve the previous image when an update fails.

Base reviewed: `527021ed1f80fa97b9579ca8d6db594ba1444887` on `main`.

## Environment and baseline

- Python 3.12.14; Pillow 12.3.0; Node 24.22.1; Playwright 1.62.1.
- The 85 Python/HTTP baseline checks passed. The remaining browser test could not launch its two scripts because the bundled Playwright Chromium executable was absent.
- Playwright's browser CDN returned an HTML page instead of an archive. Chrome for Testing 134.0.6998.35 headless shell was downloaded from Google's Chrome for Testing storage and used through the documented `E2E_CHROMIUM_EXECUTABLE_PATH` test-only override. No default system browser or product dependency was changed.
- All fixtures were fictional; weather was fake and calendar network calls in tests were injected test doubles. No external provider account, physical device or production service was used.

## Final validation

Command (set `E2E_CHROMIUM_EXECUTABLE_PATH` to the installed headless-shell executable):

```bash
E2E_CHROMIUM_EXECUTABLE_PATH=/path/to/chrome-headless-shell \
  python3 -m unittest discover -s tests -v
```

Actual final test summary:

```text
Ran 97 tests in 41.873s

OK
```

There were no skipped tests. The browser test runs three scripts as subtests:

| Script | Verified behaviour | Result |
|---|---|---|
| `phone_edit.js` | Sign-in, shopping edits/removal, private event, changed preview, 600×800 dimensions | Pass |
| `admin_calendar.js` | Admin/member controls, location, pasted and feed calendar flows, Shortcuts tokens | Pass |
| `preview_refresh.js` | Timer-driven update after another client's edit, preserved drafts, unchanged-image 304, failed-refresh retention, recovery and sign-out cleanup | Pass |

Additional new checks verify household-time-zone midnight rollover after the BST transition, imported-event selection, worker operation without requests, unchanged file timestamps/hashes, weather TTL and stale weather, atomic-write failure, invalid-image rejection, household-specific fallback, persisted sessions/data across an HTTP server restart, fallback after restart, authentication and first-frame 503 behaviour.

`python3 -m compileall -q app tests`, JavaScript syntax checks and `git diff --check` also passed. Fault-injection tests deliberately produce generic frame-refresh warnings; exception text and family content are not logged.

## Changes and operational limits

- `app/frames.py`: local frame worker, validation, content hash and household-specific persisted fallback.
- `app/render.py`: temporary-file publication with atomic replacement.
- `app/server.py`: worker lifecycle, authenticated conditional PNG responses, stale headers and 503 when no saved frame exists.
- `app/store.py`: injectable timestamp for household-local date calculation.
- `app/static/app.js` and `app/index.html`: independent preview polling, decode-before-display, form preservation, status and sign-out cleanup.
- Tests and roadmap/README/checklist updated with the current implementation and remaining gates.

Saved PNGs contain household information and live beside the database. Back up/protect them with the database; they are not a public static directory. An unchanged frame is not rewritten. A failed frame update keeps the last verified frame and marks it stale; an old weather forecast has its own visible age. The periodic worker does not fetch calendar feeds or install a device client.

Physical-size readability, Safari/accessibility, recurring calendars, automatic feed refresh, encrypted feed URLs, Shortcut retry/idempotency, broader concurrency, backup/restore, live weather and the 72-hour soak remain outstanding. The complete original G0–G8 gates have not all passed. No Kindle connection/modification or public deployment was performed or authorised by this milestone.
