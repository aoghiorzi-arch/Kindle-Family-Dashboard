# Claude Code handover — Stage A complete, Stage B (Kindle) next

Handover version 1. **Tested commit:** run `git rev-parse HEAD` in your checkout; the commit you merged for Stage A is the one this document shipped in. Do not trust a checkout with `git status` changes. No secret values are stored in Git; tokens, passwords and key files live under `data/` (git-ignored) or paths you choose.

## Status
| Done and tested on the host (Linux, Python 3.13, fictional data) | Pending / unverified |
|---|---|
| Display token + read-only `/api/display/frame.png`, 304 support, revocation, household scoping (`DISPLAY_CONTRACT.md`) | Anything on the Kindle: rendering, sleep/wake, Wi-Fi, startup, TLS compatibility |
| Control script `scripts/kfd`, health check, clean-clone install (`INSTALL.md`) | Install on the user's actual computer; its OS is not yet confirmed |
| Loopback-only server + TLS-proxy boundary (`NETWORK_PILOT.md`) | Real TLS proxy, phone CA trust, firewall (templates only) |
| `display_client/` core: bounded download, PNG validation, atomic cache, ETag, backoff | On-device client, hooks, scheduling |
| Host smoke check `scripts/kfd smoke` | 72-hour soak, live weather, permanent hosting, backups schedule (Stage C) |

State of play: **ready for supervised Kindle connection — not "Kindle ready".**

## Setup on the user's computer
1. `scripts/kfd setup`; `app.manage add-user …`; `set-location …`; `scripts/kfd start`; `scripts/kfd smoke` (expect every line `PASS`). Backup: `python3 -m app.manage backup NEW_DIR` and keep the key (`KFD_KEY_FILE`) elsewhere; see `BACKUP_RESTORE.md`. A restore revokes all tokens: issue a new display token afterwards.
2. Issue a display token (admin → Tokens → Display). Save it to a 0600 file on the computer; it is shown once.
3. Try the client on the computer first: copy `deploy/display_client.example.json`, then `python3 -m display_client config.json --once`. Expected output: `updated`, then `unchanged`.

## Questions for the user before touching the device
Exact model and firmware version (Settings → Device Options → Device Info), any earlier modification, battery condition and casing, whether the Kindle is registered to an Amazon account they care about, which computer OS, whether a spare device exists. Use `HARDWARE_AUDIT_CHECKLIST.md`. Do not record or publish the serial number.

## Stage B rules (from MASTER_PLAN_V2.md)
- The user is present and approves each concrete device operation. This handover is not authority to connect, jailbreak, flash or modify the device.
- Start read-only (USB identification). No firmware update, no automatic installer, no universal jailbreak script. Establish what backup/recovery really exists first; document risks and get approval for the specific modification.
- Research the exact supported route for that model/firmware. Prefer a small client on the existing OS; replacing firmware is out of scope.
- Resolve the TLS question (`NETWORK_PILOT.md`) with the real device. If secure transport cannot work, stop and propose an architecture; never disable certificate checks.
- Device holds only the display token. Prove one image on screen, then a webpage edit appearing after the next poll; record refresh time and readability.
- Then test Wi-Fi loss, server outage, invalid download, sleep/wake, reboot, uninstall, ghosting, charging. The old image must stay on any failure.

## Stop / uninstall
Server: `scripts/kfd stop`. Revoke the Kindle's token in the web UI (immediate). Remove the device client following whatever procedure Stage B documents before it is installed; do not install anything without a written removal step.

## Known issues
- Pre-existing before Stage A and fixed in it: a start-up race made `test_failed_first_frame_returns_503_and_cannot_bypass_auth` fail, and `shutdown()` returned before background workers finished. Full suite: 214 tests pass on Linux/Python 3.13 in a venv from `requirements.txt` (without it, calendar tests fail for missing `icalendar`).
- Not tested here: macOS/Windows, a real TLS proxy, any Kindle.
