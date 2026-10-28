# Recovery and concurrency hardening — 28 October 2026

Base: upstream `797ec57961f7641083ed0504ed1b9633ec593b2f` (merged PR #5). This is a compatible follow-up to its directory-based backup CLI and JSON `request_id` API, using local software and fictional data. No real provider, hosting or Kindle operation was performed.

## Result

**181 tests passed, no skips**, in 68.960 seconds, including all three Playwright workflows (phone edits/private events, admin calendar/feed controls and preview refresh/failure recovery). Python compilation, JavaScript syntax and whitespace checks passed. The existing 149 tests remain covered; 14 additional snapshot/recovery tests and 18 additional Shortcut/concurrency tests extend them. The original recovery integration test now verifies credential reset rather than reusing a recovered token.

Runtime: Python 3.12.14, SQLite 3.53.1, Node 24.22.1, Playwright 1.62.1, cryptography 50.0.2, Pillow 12.3.0 and icalendar 7.3.0. Browser checks used Chrome for Testing headless shell 134.0.6998.35 with the optional executable-path override. Reproduce after installing requirements, Playwright and Chromium:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q app tests
node --check app/static/app.js
git diff --check
```

For a separately installed browser, set `E2E_CHROMIUM_EXECUTABLE_PATH=/path/to/chrome-headless-shell`. Check the summary: missing Node/Playwright causes the existing browser wrapper to skip.

## Evidence

- WAL writes committed with the source connection still open appear in snapshots. A second connection inserts shopping pairs transactionally during snapshot creation; verification finds complete pairs.
- Private snapshots retain multiple households and encrypted sources but exclude keys and frames. Recovery uses the original key externally and does not change the live database. No adjacent replacement key is created.
- Recovered sessions and retry receipts are cleared, tokens revoked and automatic feeds paused. Offline recurrence expands and a fresh PNG renders. A restarted HTTP server rejects the old cookie/token and accepts an existing password.
- Missing/wrong keys, corrupt files, unauthenticated fields, foreign-key errors and executable triggers are rejected. Existing files and dangling symlink targets are not overwritten. Injected copy failure removes staging files; a destination-creation race preserves the competing file. Work/size bounds and CLI backup/verify/restore exit codes are checked.
- Eight simultaneous identical IDs on separate SQLite connections create one item; eight distinct IDs preserve eight additions. IDs remain isolated between tokens/households. Deletion and HTTP/database restart preserve duplicate protection.
- A stale authorized row is rejected after scope removal or revocation. A revocation transaction completing before a waiting addition prevents that addition. Token identity, current permission and insertion share one write transaction, including unkeyed writes.
- Receipt and shopping insertion roll back together on an injected write failure. Existing matching requests replay at capacity while new requests receive 429. Replacing a token creates a fresh scope; clients must inspect pending actions before switching.
- Existing JSON request IDs and 201/200/409 behavior are preserved. Invalid IDs/titles do not consume receipts; a temporary write failure returns a sanitized 503. There is no time expiry and no new header requirement.

## Limits

Only feed addresses/raw sources have field encryption; snapshots include ordinary household records and password/token hashes. Keep key backups separate and protect both storage locations. Structural verification does not authenticate every unencrypted record. The supported schema must match this app version; snapshots are limited to 256 MiB and copy/verification each have a 30-second work budget.

Restoring changes the recovered copy's credential/feed state intentionally: sign in, issue fresh Shortcut tokens and re-enable feeds explicitly. Password changes made after a snapshot are absent from it. A crash may leave a private unpublished staging directory; a sync error after publication may leave a complete destination, which should be verified.

Manual commands do not provide scheduling, remote retention or key rotation. A client offline queue, actual-machine recovery/key custody, Safari/accessibility review, clean-install CI, broader audit requirements, the 72-hour soak, paper readability acceptance and hardware/production gates remain open.
