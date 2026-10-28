# Kindle Family Display — local Family Hub prototype

A **local-only** prototype of the family display and its phone editor. No Kindle access is attempted, and there are no external accounts, public services or credentials. Use fictional data only.

## Run on a Mac or Linux machine with Python 3 (tested on 3.13)

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt

# One-time setup: create the household and its members (you will be asked for passwords)
python3 -m app.manage add-user sam
python3 -m app.manage add-user jo
python3 -m app.manage seed-demo        # optional: sample shopping and events
python3 -m app.manage set-location 51.5074 -0.1278 Europe/London   # for a computed sunset

python3 -m app.server
```

Open **http://127.0.0.1:8765**, sign in, and edit the shopping list or events. The preview regenerates after each successful edit.

The database is `data/family.sqlite3` (git-ignored). Override the location with `KFD_DB=/path/to/file.sqlite3`.

**Do not expose this server to a LAN or the internet.** It binds to loopback and serves plain HTTP, so it has no transport encryption. Session cookies are `HttpOnly` and `SameSite=Strict`, but the `Secure` flag is omitted until HTTPS exists.

## Security in this prototype
- Passwords are hashed with scrypt (standard library). Usernames are case-insensitive.
- Sessions use random tokens; only their SHA-256 hash is stored. Sessions expire after 14 days and are deleted on sign-out.
- Every write needs a CSRF token and a same-origin `Origin` header.
- Five failed sign-ins for a username block further attempts for 15 minutes (in memory, resets on restart).
- Each household sees only its own shopping and events. Item IDs from another household return 404.
- Responses carry a Content-Security-Policy, `X-Frame-Options: DENY` and `no-store`.
- Private events display as **Busy** on the rendered frame.

## Render a standalone PNG

```bash
python3 -c 'import json; from pathlib import Path; from app.render import save_frame; print(save_frame(json.loads(Path("app/seed.json").read_text()), "output/today.png"))'
```

The PNG carries 167 ppi metadata (Kindle Touch density), so printing at 100% shows the physical size.

## Run the tests

```bash
python3 -m unittest discover -s tests -v
```

The end-to-end tests (`tests/test_e2e.py`) check that a phone edit changes the next preview and that the preview matches the saved data. Two browser tests drive the real pages with Playwright: `tests/e2e/phone_edit.js` (shopping, private events, the preview) and `tests/e2e/admin_calendar.js` (members, location, calendar import and clear, Shortcuts tokens, the member view). They run when `node` and the `playwright` package are installed, and are skipped otherwise.

## Scope
- Today renderer: 600×800 PNG, deterministic for the same input. Fonts are bundled in `app/fonts/` (Lato and Noto Serif, SIL Open Font License; see `app/fonts/OFL-Lato-NotoSerif.txt`).
- Family Hub: SQLite storage, sign-in, one household with two member accounts, shopping (add, mark got, remove), events (add with optional time and private flag, remove).
- Weather: server-side adapter with a 30-minute cache. The demo uses `FakeProvider` (fixed values from `app/seed.json`) only. Displays never call a weather service. If a refresh fails, the last good forecast is kept and shows "Updated N h ago" once it is over an hour old.
- Sunset: computed from the household location and time zone when set (`set-location`). Without a location, the fixture value is used.
- Admin settings (admins only): add members with a role (member or admin), set the location for sunset, and create or revoke Shortcuts tokens. The first member of a household is an admin. Use `add-user NAME --admin` to add another admin from the command line.
- Family calendar (admins only): paste an `.ics` export in Household settings. The server never fetches a URL. Only today's events are shown, in the household's time zone. Recurring events are skipped, and the import reports how many. Private events show as "Busy". Imported events can be removed at any time.
- Calendar feeds (admins only, up to three): add a read-only `https://` calendar address in Household settings, or refresh one by hand. The server downloads it, and only today's events are shown. Protections:
  - https only, standard port, no login in the address, no redirects followed;
  - the host must resolve to a public address, and the connection is made to that exact address;
  - responses are limited to 2 MB and 10 seconds;
  - feed addresses are never shown again after saving (the phone shows only the host) and never appear in error messages.
  - Refresh runs when you press Refresh, or with `python3 -m app.manage refresh-feeds`. The display never fetches. Schedule that command for automatic refresh once the machine is set up.
  - Feed addresses are stored in the local database as plain text. Encrypt them at rest before any deployment.
- Shortcuts: a token can only add shopping items (`docs/SHORTCUTS.md`). Tokens are stored as hashes and can be revoked.
- Daily thought: a King James Version verse chosen by date (the same verse all day), bundled in `app/content.py`. No network calls. Check each verse against a printed Bible before it goes on a family display.
- A real weather provider makes external network calls and needs separate approval before it is added.
- Not included: recurring-event expansion, automatic feed scheduling, encryption of stored feed addresses, live weather, Shortcuts credentials, Kindle device support, HTTPS, production hosting, and any device bridge.

For execution priorities and gates see `MASTER_PLAN_V2.md`. The read-only hardware checklist is in `docs/HARDWARE_AUDIT_CHECKLIST.md`. The original detailed plan is preserved in `docs/ORIGINAL_MASTER_PLAN.md`.
