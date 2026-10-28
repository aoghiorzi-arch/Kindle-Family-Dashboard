# Calendar storage verification — 28 October 2026

Base: merged PR #4, upstream `15dd172ec38f65320a1ca2182276d7a08aecbadb`. Local-only software and fictional data; no real calendar provider, Kindle access or deployment.

## Result

**139 tests passed, no skips** (66.348 seconds), including all three existing Playwright workflows. The earlier 124-test suite also passed after encryption was introduced. Python compilation, JavaScript syntax, `git diff --check` and `python3 -m pip check` passed.

Runtime: Python 3.12.14, SQLite 3.53.1, Node 24.22.1, Playwright 1.62.1, Pillow 12.3.0, cryptography 50.0.2 and icalendar 7.3.0. Browser checks used the existing Chrome for Testing headless shell 134.0.6998.35 with the optional executable-path override.

Reproduce from the repository root after installing requirements, Playwright and Chromium:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q app tests
node --check app/static/app.js
python3 -m pip check
git diff --check
```

If using a separately installed browser, set `E2E_CHROMIUM_EXECUTABLE_PATH=/path/to/chrome-headless-shell` for the test command. Missing Node/Playwright causes the existing browser wrapper to skip; verify the summary has no skips.

## New checks

`test_calendar_secrets.py` adds 13 storage/migration checks:

- Secret URL/source sentinels absent from SQL exports and current database bytes; only encrypted fields are stored and APIs decrypt correctly.
- Separate 32-byte key, owner-only file permissions, distinct ciphertext for repeated content and restart with the same key.
- Missing, wrong or malformed keys refuse access without regeneration or database mutation; unsafe POSIX permissions and symlinks refuse access.
- Ciphertext substitution across feed IDs, households and field purposes fails authentication. Tampered ciphertext and plaintext injected into an encrypted database are rejected without exposing values.
- An explicitly configured external original key opens a copied matching database; no adjacent replacement key is generated. This is a fixture-level recovery check, not a backup service or live restore procedure.
- Missing metadata cannot trigger a replacement key when encrypted rows remain.
- Legacy conversion preserves IDs, parsed events and manual schedule defaults, and removes raw-source/URL sentinels from current SQLite logical files.
- Simulated encryption failure rolls back all fields/metadata; retry reuses the original key. Simulated VACUUM failure locks normal connections until cleanup resumes, without double encryption.
- A legacy WAL database converts and its source sentinel is absent from the resulting current logical files.

`test_storage_http.py` adds two HTTP checks: lost keys return sanitized 503s for read/write/image routes without recreating the key; corrupted field data never appears in the response and saved events remain intact. Restoring the original key resumes access.

The unchanged calendar worker tests verify scheduled refresh/retry/restart, offline recurrence, source replacement/deletion and timezone races against encrypted storage. Existing browser tests exercise calendar import/feed controls, phone edits, privacy, preview polling/failure recovery and sign-out.

## Limits and next work

Encryption applies to feed addresses and raw calendar source text. Derived event records, labels, other household records and PNGs remain sensitive ordinary data. Database-only field encryption does not protect a database plus key copied together, a compromised server, or historical backups/snapshots/storage remnants. Migration must run with all old/new processes stopped. New connections fail closed on key errors; existing connections retain their loaded key.

Automated backup/restore with separate key custody, rotation tooling, broader concurrency/Shortcut idempotency, HTTPS/hardened hosting and a 72-hour soak remain open. The paper readability review, hardware assessment and separate deployment/device approvals also remain open. This batch does not establish production readiness.
