# Kindle Family Display — first local demo

This is a safe **Mac/local-only demonstration** of the proposed single-screen-first family display. No Kindle access is attempted. No accounts, public services or credentials are required.

## Run on a Mac with Python 3

```bash
cd Kindle-Family-Dashboard
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m app.server
```
Open **http://127.0.0.1:8765** on the same Mac. Add a shopping item or an event and watch the display PNG regenerate. **Do not expose this HTTP server to a LAN or the internet:** it is an unauthenticated in-memory mock and intentionally binds to loopback only. Don't use real family information in this prototype.

Generate a standalone PNG:

```bash
python3 -c 'import json; from pathlib import Path; from app.render import save_frame; print(save_frame(json.loads(Path("app/seed.json").read_text()), "output/today.png"))'
```

The PNG carries 167 ppi metadata (Kindle Touch density), so printing at 100% shows the physical size.

Run the tests:

```bash
python3 -m unittest discover -s tests -v
```

## Scope
- Functional Today image renderer: 600×800 PNG with deterministic image bytes given the same input and fonts.
- Fake date/weather/sunset/events/shopping/thought. Sample values are fictitious.
- Local editing form for quick-add shopping and calendar entries; in-memory storage only, resets on restart.
- Marking an event `private` in renderer input replaces its displayed title with “Busy”.
- Tests of dimension, determinism, input-change hashing and private-title masking.
- This mock has *no login, database, calendar providers, live weather, Shortcuts credential handling or device support*.
- Fonts are bundled in `app/fonts/` (Lato and Noto Serif, SIL Open Font License; see `app/fonts/OFL-Lato-NotoSerif.txt`), so the same input gives the same bytes on any machine with the same Pillow version.

For execution priorities and gates see `MASTER_PLAN_V2.md`; the read-only hardware checklist is in `docs/HARDWARE_AUDIT_CHECKLIST.md`. The original detailed plan is preserved in `docs/ORIGINAL_MASTER_PLAN.md`.
