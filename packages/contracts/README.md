# Kindle snapshot contract (v1)

- Schema: [`kindle-snapshot.v1.schema.json`](kindle-snapshot.v1.schema.json) (JSON Schema draft 2020-12, `additionalProperties: false` throughout).
- Validator: [`validate.py`](validate.py) adds the checks the schema cannot express: `expiresAt` after `generatedAt`, and `weather.updatedAt` not after `generatedAt`.
- Fixtures: `tests/fixtures/snapshots/valid/` and `invalid/`. All data is synthetic.

## Rules
- Field limits are part of the contract. Exceeding one makes the snapshot invalid. The cloud must not truncate silently; it sends `overflow` counts instead.
- Private calendar events must be labelled `Busy` (enforced by schema).
- No credential, token, URL or edit endpoint may appear in a snapshot. Extra fields are rejected.
- Null means "unavailable" and renders as an explicit empty state, never as zero.
- Breaking changes increment `schemaVersion`. The device must refuse unknown major versions and keep its last good snapshot.

## Validate
```bash
python3 -m unittest tests.test_snapshot_contract tests.test_snapshot_simulator
```
