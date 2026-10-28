# Local server installation (A2)

Supported by the scripts: **macOS and Linux with Python 3.11+** (tested on 3.13). Windows is not yet supported by the scripts: use WSL2 (Ubuntu) until the computer's OS is confirmed. Calendar parsing resource limits are Unix-only.

```bash
git clone <repo> && cd Kindle-Family-Dashboard
scripts/kfd setup                  # venv, pinned dependencies, database + calendar key under data/
.venv/bin/python -m app.manage add-user sam      # prompts for a password; first user is admin
.venv/bin/python -m app.manage add-user jo
.venv/bin/python -m app.manage seed-demo         # optional, fictional items
.venv/bin/python -m app.manage set-location 51.5074 -0.1278 Europe/London
scripts/kfd start                  # background, loopback only
scripts/kfd status                 # running / healthy
scripts/kfd stop
```

`scripts/kfd run` runs in the foreground; `scripts/kfd smoke` runs the host-side end-to-end check in a throwaway directory with fictional data (server, display token, display client, phone edit, revocation).

## Files and configuration
| What | Default | Override |
|---|---|---|
| Database | `data/family.sqlite3` | `KFD_DB` |
| Frames | `<database>.frames/` | — |
| Calendar encryption key | `data/family.sqlite3.key` | `KFD_KEY_FILE` (keep it on different storage from backups) |
| PID / log | `data/server.pid`, `data/server.log` (no request or secret logging) | `KFD_DATA_DIR` |
| Port | `8765` | `KFD_PORT` |
| Settings file | `data/kfd.env` (copy `deploy/kfd.env.example`) | `KFD_ENV_FILE` |

The server listens on **127.0.0.1 only**; it refuses any other `KFD_HOST`. Network access is via the TLS proxy described in `NETWORK_PILOT.md`.

## Verified
From a fresh `git clone`: `setup`, `start`, `status` (healthy), `stop` and `smoke` all passed on Linux (Python 3.13) with fictional data. macOS and the user's actual computer are not yet verified.
