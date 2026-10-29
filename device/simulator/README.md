# Desktop simulator (Phase 2)

Renders a contract v1 snapshot to a 600×800 PNG on a desktop, for preview and tests.

```bash
python3 -m device.simulator tests/fixtures/snapshots/valid/full.json /tmp/full.png
```

- Validates the input against `packages/contracts/kindle-snapshot.v1.schema.json` first; invalid input is refused.
- Uses the existing Today renderer (`app/render.py`). The renderer draws only the first three events, the shopping count and the weather age. News and the clock are not drawn yet.
- Not a device test. It shows layout and content only. Physical legibility, ghosting and refresh need the H2 gate.
