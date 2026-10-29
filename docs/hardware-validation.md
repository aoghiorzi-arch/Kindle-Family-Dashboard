# Hardware validation — Kindle Touch D01200

**Status: H0 NOT PERFORMED. Every result below is UNVERIFIED until the owner records it.**

This document is the H0 (non-invasive readiness) and H1 (recovery feasibility) record for [`SERVERLESS_MASTER_PLAN.md`](SERVERLESS_MASTER_PLAN.md) §2. It replaces nothing in [`HARDWARE_AUDIT_CHECKLIST.md`](HARDWARE_AUDIT_CHECKLIST.md); this file is the serverless plan's gate record.

## Rules

1. **No device modification.** Nothing here authorises jailbreak, firmware update, flashing, rooting, installing software, writing to the system partition, or a factory reset.
2. **Read-only first.** Identify and copy; do not edit, delete or rename anything on the Kindle.
3. **Redact identifiers.** Do not record the serial number, MAC address, Amazon account details or Wi-Fi names/passwords in this repository. Note "redacted" instead.
4. **Record what is seen.** Write "unknown" where unknown. Do not infer success.
5. **Safety stop.** Any swelling, heat, leakage, casing gap or instability: stop, unplug, and do not charge unattended.
6. **Backups are not recovery images.** A copy of user-visible USB storage is useful for data safety only. It is not a firmware or system backup (plan §0, item 8).

## H0 — non-invasive readiness (owner-led, on the Mac)

Run these in Terminal on the Mac, with the Kindle connected by USB and the owner present. They only read from the device.

### H0.1 Identify the volume (read-only)

```bash
ls /Volumes                       # note the Kindle volume name, e.g. "Kindle"
diskutil list                     # note the device/size; do not paste serial values
df -h /Volumes/<Kindle-volume>    # free space as seen by the Mac
```

Record: volume name (ok to keep), total and free space, file system type from `diskutil info /Volumes/<Kindle-volume>` (redact the UUID).

### H0.2 Inventory folders without changing them

```bash
find "/Volumes/<Kindle-volume>" -maxdepth 2 -not -name '.*' | sort > ~/KindleInventory-$(date +%F).txt
```

Review the inventory for folders that suggest earlier modification or unknown software. Examples to note, not conclude from: `extensions`, `KUAL`, `MRPI`, `usbnet`, unexpected `.sh`/`.bin` files, or any folder you do not recognise. Record counts and names of suspicious folders only, not file contents.

### H0.3 Backup — waived by owner (29 October 2026)

The owner reports the device holds no user content, so no backup is being made. This waives the plan's §2 backup requirement for H0 only. H0.2 still lists what is on the volume, to confirm that claim. If anything personal turns up, stop and make a backup before continuing.

### H0.4 Safe eject and reconnect

```bash
diskutil eject "/Volumes/<Kindle-volume>"
```

Unplug, wait 10 seconds, replug. Confirm the volume mounts again and the file count matches the inventory. Record the result.

### H0.5 On-device checks (menus only; no changes)

| Check | How | Result |
|---|---|---|
| Model marking | Back of device | UNVERIFIED |
| Firmware version | Settings → Device Info | UNVERIFIED (expected 5.3.7.3) |
| Clock and timezone | Settings / Device Options | UNVERIFIED |
| Wi-Fi reconnects after reboot | Reboot via the device's own menu; note whether it rejoins | UNVERIFIED |
| Battery and charging | Observe while plugged in for 30 minutes; check casing for swelling and heat | UNVERIFIED |
| Screen | Ghosting, legibility at normal distance | UNVERIFIED |
| Registration status | Settings (record yes/no only) | UNVERIFIED |

### H0.6 Decision

| Gate | Status |
|---|---|
| H0 complete | Yes, owner-reported (29 October 2026) |
| Ready for H1 review | No |

Attach results in a new section below, dated, with redactions. Do not paste raw inventories containing personal book titles or folder names.

## H1 — jailbreak and recovery feasibility

Not started. See [`jailbreak-recovery-review.md`](jailbreak-recovery-review.md). H1 needs written owner consent before any research becomes device action.

## Results log

### 29 October 2026 — owner, from Mac Terminal (read-only)

| Step | Result | Status |
|---|---|---|
| H0.1 Volume | Mounted as `Kindle`, MS-DOS FAT32, 3.2 GiB, 2.6 MiB used, 3.4 GB free | Done |
| H0.2 Inventory | Only default content: `documents/` (Kindle User's Guide and its sidecar), `system/`, `audible/`, `music/`, `.active_content_sandbox/`. No `extensions`, `KUAL`, `MRPI`, `usbnet` or unexpected scripts. macOS wrote `.fseventsd/` on mount. `.Spotlight-V100` was not readable (no user content). Inventory kept on the Mac, not in the repo. | Done |
| Firmware (`system/version.txt`) | `Kindle 5.3.7.3` (build shown in file). Matches the plan. | Done; confirm against the on-device menu in H0.5 |
| H0.3 Backup | Waived by owner: device reported empty. Inventory consistent with that. | Waived |
| H0.4 Eject | `diskutil eject` succeeded. Owner reports the reconnect step as satisfactory. | Done (owner-reported) |
| H0.5 On-device checks | Owner reports all checks satisfactory. Individual values (clock, Wi-Fi after reboot, battery, screen, registration) were not supplied and are not recorded here. | Done (owner-reported, values not recorded) |

H0 complete on the owner's report. Per-item values, especially battery and casing observations, are not in this log; if they are needed for the H1 gate, the owner should add them.
