# Recovery and Shortcut retry verification — 28 October 2026

The full suite passed 147 tests with no skips, including all three Playwright browser workflows. Two additional recovery integration tests were then added; all six backup tests passed. Total verified tests: 149. Python compilation and `git diff --check` also passed.

New coverage:
- A committed WAL snapshot restores shopping, feed addresses and calendar source text using a separately stored key; later live edits do not change the snapshot.
- Wrong/missing keys, altered ciphertext, existing destinations and publication failures do not produce a completed recovery directory or overwrite data.
- Recovered sessions are cleared; source sessions remain intact; private file/directory permissions are enforced.
- Recovered recurring calendars extend offline after restarting with the same key; Shortcut token hashes and retry receipts survive recovery.
- CLI backup and restore work with explicit database/key paths and reject an existing destination.
- Parallel identical Shortcut requests create one item; a reused ID with a different title returns 409.
- Retry receipts survive deletion of shopping items, are scoped to the token and do not bypass revocation. Legacy requests without an ID still add each time.
- Failed receipt insertion rolls back the shopping insertion, allowing a subsequent retry to succeed.

Reproduction:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q app tests
git diff --check
```

For browser workflows, install Playwright/Chromium as described in README. Verification used the available Playwright package through NODE_PATH and a local Chromium executable through E2E_CHROMIUM_EXECUTABLE_PATH.

Limits: backup scheduling and off-machine/key backup custody are operator responsibilities. Restore validates logical database integrity and encrypted fields, not storage hardware durability. Backup contents other than encrypted calendar fields remain readable. Recovery preserves enabled feed-refresh settings. Physical display acceptance, broader concurrency/soak testing, production deployment and Kindle hardware work remain open.
