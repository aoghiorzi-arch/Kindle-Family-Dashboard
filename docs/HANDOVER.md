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

## Device and decision record (added 2026-11-14)

Confirmed by the user from the device (no serial or MAC recorded here):

| Item | Value |
|---|---|
| Model label | D01200 (matches the plan's 600×800 Kindle Touch assumption) |
| Firmware | 5.3.7.3 |
| Network | Wi-Fi only |
| Registration | Unregistered (not linked to an Amazon account) |
| Free space | about 3.2 GB |
| Not yet known | prior modification, battery/casing condition, whether it shows Special Offers (ads) |

Server: Dell Inspiron 3558 (i5-5200U, 3.9 GB RAM), Ubuntu Server 26.04.1 LTS, fixed LAN address 192.168.1.139, reached over SSH. `scripts/kfd setup` and `smoke` passed there on 2026-11-14 (all 7 checks). Always-on setup, proxy and firewall: `UBUNTU_SERVER.md` (unverified on the machine). The Windows laptop path is not supported by `scripts/kfd`.

**Decision (user, 2026-11-14): Option 1 — jailbreak the Kindle and run a small client on it that fetches the picture from the Family Hub server.** Not chosen: VNC kiosk (needs another machine, poor e-ink behaviour), custom-screensaver module (sleep screen only, ad-free models only), Samsung tablet (kept as a possible later second display). The Kindle stays display-only: no edit rights, no taps for now.

Desk research summary, **unverified on this device**. MobileRead and several blogs could not be read in the cloud session, so the Stage B session must read them directly:
- Community sources describe 5.3.7.3 as the last firmware for this hardware and the standard K5 jailbreak route (documented for 5.0.0–5.4.4.2) as covering it; a newer universal jailbreak thread reportedly covers firmware before 5.8.8. Check the MobileRead *Kindle Touch Hacking* wiki page and the current jailbreak thread for the exact package, steps and warnings.
- Typical follow-on tools: KUAL launcher, USBNetwork + SSH (set a root password; default is blank), then a fetch-and-display script using `eips`. Reference design: github.com/pascalw/kindle-dash (tested on Kindle 4 NT, not the Touch). github.com/bishopdynamics/kindle-touch-kiosk confirms the D01200 on 5.3.7.3 can be jailbroken and run custom software.
- No jailbreak-free way to set custom images was found.
- Recovery: one forum user reported recovering a stuck Touch with a tool called Kubrick. Not confirmed. A documented, tested recovery path, plus a USB copy of the device contents, must exist **before** the user approves any modification.
- Built-in `curl`/`wget` are reportedly unreliable for modern HTTPS; kindle-dash ships its own client. Whether it runs on the Touch and can trust our certificate authority is the open Stage B question (`NETWORK_PILOT.md`).

Stage B order: (1) confirm hardware condition and read the current guides; (2) user-approved read-only USB identification; (3) backup copy and recovery plan, then explicit approval of the specific jailbreak step; (4) prove an image on screen from our server over a working secure transport; (5) phone edit appears on the next poll; (6) failure and power tests.

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
