# D1 runtime spike — can the Python logic run in a Cloudflare Worker?

**Date:** 29 October 2026 · **Decision record:** [`adr/0001-serverless-offline-first.md`](adr/0001-serverless-offline-first.md) D1 · **Status:** partly complete. The Pyodide runtime could not be run from this session.

## Question

Should the Worker be TypeScript (the accepted default), or should the existing Python logic run in Python Workers?

## What was checked, and how

| Check | Method | Result |
|---|---|---|
| Pure-Python packages on PyPI | PyPI JSON API | `icalendar` 7.3.0, `recurring-ical-events` 3.8.2, `python-dateutil` 3.0.0 and `tzdata` have pure-Python wheels. |
| Pyodide (WebAssembly) builds on PyPI | Searched release files for `emscripten`/`wasm32`/`pyodide` tags | **None** for Pillow, cryptography, or the pure-Python packages above. Pyodide ships its own builds, so this does not decide the question. |
| Cloudflare Python package rules | Web search only. The Cloudflare docs (`developers.cloudflare.com`) and Pyodide docs (`pyodide.org`) could not be fetched from this session. | Search snippets say pure-Python packages and Pyodide-bundled packages work. Pillow support was positive but not official. Cryptography: no source found. |
| Workers limits | Web search only; official page not fetched. | Snippets report 10 ms CPU on Free, 5 min max on Paid (30 s default), 128 MB memory, 64 MiB uncompressed bundle. These come from secondary sources and need checking. |
| Local `wrangler dev` with Python | Not run. The npm registry is reachable (latest `wrangler` 4.155.0), but Pyodide packages come from `cdn.jsdelivr.net`, which is unreachable. | Blocked. |
| CPU cost of current logic, CPython on this container | Timed `app.render` (600×800 PNG) and `app.ics.parse_events` (one weekly series, 52 occurrences, 10 runs) | Render: median ~180 ms. ICS parse including its subprocess: median ~190 ms, most of it interpreter start-up. |

## Findings

1. **Calendar parsing is not a straight port.** `app/ics.py` runs the parser in a child process (`subprocess.run(... '-m', 'app.ics', '--worker')`) with a wall-clock deadline and a memory/CPU ceiling. A Worker cannot spawn a process. The isolation has to be rebuilt, for example as a bounded TypeScript parser with strict input limits, or as a separately deployed parsing service. This does not depend on Python vs TypeScript.
2. **Pillow and cryptography only matter if the server renders PNGs or encrypts stored feed URLs.** Both are needed for the server-PNG path (D4 fallback) and for the current `app/secrets.py` key-file design. The accepted default changes both: the Kindle renders from JSON (D4), and storage uses Worker secrets (ADR D3, plan §3). Under the defaults, the Worker needs neither package.
3. **CPU budget rules out server rendering on Free.** At ~180 ms on a fast machine, a Pyodide render would be slower still. Even with the 10 ms figure unverified, server rendering would need a Paid plan. This supports keeping rendering on the device.
4. **Pure-Python parts port cheaply.** Sunrise and sunset (`app/solar.py`) and the recurrence rules can move to TypeScript with the existing Python tests as an oracle.

## Result for D1

- **Accepted default stands:** TypeScript Worker, with logic ported into `packages/core`.
- **Python Workers are not recommended** for this project. Two of the three dependencies are unverified, and the ICS isolation would be rebuilt either way.
- **Not closed:** the Pyodide runtime tests for Pillow and cryptography. They become unnecessary under the default D4 and D3 choices. If D4 later falls back to server PNGs, they must be re-run from a session that can reach Pyodide.

## Follow-ups

| Item | When |
|---|---|
| Fetch the Cloudflare Python package and limits pages from a session that can reach them, then record the results here. | Before any Python-Worker decision |
| TypeScript ICS parser, tested against the existing Python ICS fixtures, with strict input limits | Phase 5 (calendar adapter) |
| Replace the feed-URL key file with Worker secrets; use Web Crypto for stored-field encryption | Phase 3 |
| Port `app/solar.py` to `packages/core` with fixtures | Phase 3 |
| Confirm the Free and Paid CPU limits from the official page before choosing a plan | Phase 3 |
