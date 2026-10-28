# Kindle Family Display — local Family Hub prototype

A **local-only** prototype of the family display and its phone editor. No Kindle access is attempted, and there are no external accounts, public services or credentials. Use fictional data only.

## Run on a Mac or Linux machine with Python 3 (tested on 3.13)

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m app.manage init-db          # offline initialization/calendar-storage migration

# One-time setup: create the household and its members (you will be asked for passwords)
python3 -m app.manage add-user sam
python3 -m app.manage add-user jo
python3 -m app.manage seed-demo        # optional: sample shopping and events
python3 -m app.manage set-location 51.5074 -0.1278 Europe/London   # for a computed sunset

python3 -m app.server
```

Open **http://127.0.0.1:8765**, sign in, and edit the shopping list or events. The preview updates after each successful edit and checks automatically every minute while the tab is visible. Returning to the tab or reconnecting also triggers a check. Failed updates keep the last displayed image; polling preserves unfinished form entries.

The database is `data/family.sqlite3` (git-ignored). Verified per-household frames are saved in `data/family.sqlite3.frames/` beside it. Treat both as private household data; neither is a public static directory. Override the location with `KFD_DB=/path/to/file.sqlite3`.

Calendar feed addresses and cached `.ics` source text are encrypted using a separate owner-only key file, defaulting to `data/family.sqlite3.key`. Preserve this key: a database copy alone cannot recover these fields. Set `KFD_KEY_FILE` to a protected path outside the application/data backup directory for separate key custody. The app creates a key on first initialization, but never replaces a missing key for an encrypted database. Stop all Family Hub processes before upgrading/migrating. See [`docs/CALENDAR_STORAGE.md`](docs/CALENDAR_STORAGE.md) for migration, key handling and remaining protection limits.

**Do not expose this server to a LAN or the internet.** It binds to loopback and serves plain HTTP, so it has no transport encryption. Session cookies are `HttpOnly` and `SameSite=Strict`, but the `Secure` flag is omitted until HTTPS exists.

## Security in this prototype
- Passwords are hashed with scrypt (standard library). Usernames are case-insensitive.
- Sessions use random tokens; only their SHA-256 hash is stored. Sessions expire after 14 days and are deleted on sign-out.
- Every write needs a CSRF token and a same-origin `Origin` header.
- Five failed sign-ins for a username block further attempts for 15 minutes (in memory, resets on restart).
- Each household sees only its own shopping and events. Item IDs from another household return 404.
- Responses carry a Content-Security-Policy, `X-Frame-Options: DENY` and `no-store`.
- Private events display as **Busy** on the rendered frame.

## Backup and recovery

Use `python3 -m app.manage backup NEW_DIRECTORY` to create a verified database snapshot. Preserve its matching encryption key separately. `python3 -m app.manage verify-backup BACKUP_DB --key-file ORIGINAL.key` checks a snapshot without migration or data changes. Use `python3 -m app.manage restore BACKUP_DB NEW_DIRECTORY` with `KFD_KEY_FILE` pointing to that key, or append `--key-file ORIGINAL.key` explicitly. Restore refuses existing destinations, clears browser sessions, revokes recovered Shortcut tokens and pauses automatic feeds. Frames regenerate locally. See [`docs/BACKUP_RESTORE.md`](docs/BACKUP_RESTORE.md) for the recovery procedure and work/size limits.

## Render a standalone PNG

```bash
python3 -c 'import json; from pathlib import Path; from app.render import save_frame; print(save_frame(json.loads(Path("app/seed.json").read_text()), "output/today.png"))'
```

The PNG carries 167 ppi metadata (Kindle Touch density), so printing at 100% shows the physical size.

## Run the tests

```bash
python3 -m unittest discover -s tests -v
```

The end-to-end tests (`tests/test_e2e.py`) check that a phone edit changes the next preview and that the preview matches the saved data. Three browser scripts drive the real pages with Playwright: `tests/e2e/phone_edit.js` (shopping, private events, the preview) and `tests/e2e/admin_calendar.js` (members, location, calendar import and clear, Shortcuts tokens, the member view). `tests/e2e/preview_refresh.js` checks automatic updates, form drafts, unchanged-frame responses, failure/recovery and sign-out. They run when `node` and the `playwright` package are installed, and are skipped otherwise. Chromium must also be installed (`node /path/to/playwright/cli.js install chromium`); an installed browser can be selected with `E2E_CHROMIUM_EXECUTABLE_PATH=/path/to/chrome-headless-shell`. Browser launch failures fail the test rather than silently skipping it.

## Automatic frame lifecycle

While the server runs, a background worker checks every household once a minute. Each check derives the current date in that household's time zone, selects today's imported events and daily verse, recalculates sunset, and refreshes the weather adapter when its 30-minute cache expires. A separate calendar worker expands saved calendar sources locally and refreshes only feeds whose admin has enabled automatic refresh. Both workers stop with the server.

Complete, verified 600×800 PNGs are written to temporary files and atomically replaced. Identical PNGs keep their existing file and hash. If rendering or writing fails, `/frame.png` serves only that household's verified saved image with `X-Frame-Stale: true`; if none exists, it returns 503. A successful render clears the stale flag. Weather age is separate: a newly rendered screen can contain a visibly old weather forecast.

`ETag` is the PNG's SHA-256 hash. Authenticated conditional requests return 304 when pixels are unchanged, avoiding image replacement in the preview. The browser decodes a replacement before showing it, retains the previous image on errors, and clears its private image on sign-out. This is a local simulator; no device polling/client is installed.

## Scope
- Today renderer: 600×800 PNG, deterministic for the same input. Fonts are bundled in `app/fonts/` (Lato and Noto Serif, SIL Open Font License; see `app/fonts/OFL-Lato-NotoSerif.txt`).
- Family Hub: SQLite storage, sign-in, one household with two member accounts, shopping (add, mark got, remove), events (add with optional time and private flag, remove).
- Weather: server-side adapter with a 30-minute cache. The demo uses `FakeProvider` (fixed values from `app/seed.json`) only. Displays never call a weather service. If a refresh fails, the last good forecast is kept and shows "Updated N h ago" once it is over an hour old.
- Sunset: computed from the household location and time zone when set (`set-location`). Without a location, the fixture value is used.
- Admin settings (admins only): add members with a role (member or admin), set the location for sunset, and create or revoke Shortcuts tokens. The first member of a household is an admin. Use `add-user NAME --admin` to add another admin from the command line.
- Family calendar (admins only): paste an `.ics` export in Household settings. The server never fetches a URL. Only today's events are shown, in the household's time zone. Daily, weekly, monthly and yearly recurrences are expanded for a rolling 31-day window; COUNT, UNTIL, EXDATE, RDATE and moved/cancelled instances are handled. The import reports occurrence and skipped-entry counts. Saved source text extends the window locally each day, without another paste. Single events retain their original dates. Events display on their occurrence start date; multi-day occupancy is not rendered across every day. Private events show as "Busy". Imported events can be removed at any time.
- Calendar feeds (admins only, up to three): add a read-only `https://` calendar address in Household settings, or refresh one by hand. The server downloads it, and only today's events are shown. Protections:
  - https only, standard port, no login in the address, no redirects followed;
  - the host must resolve to a public address, and the connection is made to that exact address;
  - responses are limited to 2 MB and 10 seconds;
  - feed addresses are never shown again after saving (the phone shows only the host) and never appear in error messages.
  - Refresh runs when you press Refresh, or with `python3 -m app.manage refresh-feeds`. An admin can also enable automatic refresh per feed in Household settings: checks run every 30 minutes while the server runs, including after a failed attempt. Existing/new feeds default to manual; the choice and last attempt survive restarts. Pause stops future automatic downloads (an in-flight download may finish). The display never fetches. A separate calendar worker keeps slow downloads out of the frame renderer. Do not schedule the management command as well as the built-in worker.
  - Feed addresses and cached source calendar text are encrypted at rest with a separate key. Parsed event records, feed labels and other household data remain ordinary SQLite fields; protect the entire database and saved frames. Sources are removed when their pasted import or feed is removed. Cached recurrence can roll forward locally even when a feed is unreachable; it reflects the last downloaded version, not live confirmation.
- Shortcuts: a token can only add shopping items (`docs/SHORTCUTS.md`). Tokens are stored as hashes and can be revoked. An optional `request_id` makes retries safe without suppressing deliberate repeat purchases. Authorization is rechecked in the insertion transaction; each token retains at most 5,000 keyed request receipts while allowing existing retries at capacity.
- Daily thought: a King James Version verse chosen by date (the same verse all day), bundled in `app/content.py`. No network calls. Check each verse against a printed Bible before it goes on a family display.
- A real weather provider makes external network calls and needs separate approval before it is added.
- Not included: full-database encryption, key rotation tooling, scheduled backups, live weather, Shortcuts credentials, Kindle device support, HTTPS, production hosting, and any device bridge.

For execution priorities and gates see `MASTER_PLAN_V2.md`. The read-only hardware checklist is in `docs/HARDWARE_AUDIT_CHECKLIST.md`. The original detailed plan is preserved in `docs/ORIGINAL_MASTER_PLAN.md`.


Current implementation checklist: [`docs/PROGRESS.md`](docs/PROGRESS.md). Verification evidence: [`docs/VERIFICATION_2026-10-28.md`](docs/VERIFICATION_2026-10-28.md).

## Review the display at physical size

Run `python3 -m app.review`, then open `data/display-review/index.html`. The self-contained HTML embeds four fictional scenarios (normal, long/stale/private/overflow, empty/unavailable, and one-item/private). Print at **100% / actual size**, without fit-to-page or browser headers/footers. Each board is 91.257 × 121.677 mm at 167 ppi; verify the 50 mm calibration line before judging readability. A paper review at the intended viewing distance remains a user acceptance step; no Kindle connection is needed. Findings: [`docs/DISPLAY_REVIEW.md`](docs/DISPLAY_REVIEW.md).

Calendar parsing uses pinned `icalendar` and `recurring-ical-events` dependencies. Each parse is isolated in a subprocess with a six-second deadline, a 500-component/occurrence cap and 31-day recurrence window; Unix additionally caps memory at 512 MiB and CPU at five seconds. Subdaily rules are reported as unsupported. Failed parses keep the previous import/feed data. The HTTPS downloader retains public-address pinning, no redirects, a 2 MB cap and a download deadline; DNS resolution still uses the operating system resolver.
