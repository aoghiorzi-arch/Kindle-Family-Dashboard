# Jailbreak and recovery review — Kindle Touch D01200, firmware 5.3.7.3

**Status: UNVERIFIED. No installation method has been identified, validated or approved.**

This is the H1 checklist from [`SERVERLESS_MASTER_PLAN.md`](SERVERLESS_MASTER_PLAN.md) §2. It is a research template. Nothing in it is a claim that the device can be modified, that a specific tool works, or that a recovery route exists.

## Principles

- **No automation.** No script, installer or package runs against the device from this repository.
- **Provenance first.** Every package, tool or document must be named, sourced, versioned and checksummed before it is considered. Unknown or mirrored binaries are rejected.
- **Firmware-specific.** A method for another model or firmware does not count. Match D01200 and 5.3.7.3 exactly, and confirm the firmware on the device first (H0.5).
- **Recovery before action.** A documented, tested way back must exist before any modification is proposed. Serial-console necessity must be stated.
- **Owner consent per action.** Each invasive step needs a separate, written approval after the owner has read this review.

## Checklist (all items UNVERIFIED)

| # | Question | Evidence required | Status |
|---|---|---|---|
| 1 | Does a published method exist for D01200 on firmware 5.3.7.3? | Primary source with date, version and author | UNVERIFIED |
| 2 | Is the device already modified? | H0 inventory and on-device check | UNVERIFIED |
| 3 | What are the package/tool versions and checksums? | Pinned list with SHA-256 from a source the owner accepts | UNVERIFIED |
| 4 | What are the prerequisites (cables, serial adapter, host OS)? | Written list, host OS confirmed as macOS | UNVERIFIED |
| 5 | What are the worst-case failures (bricked storage, boot loop, lost registration)? | Written failure analysis | UNVERIFIED |
| 6 | Is a serial console needed, and if so is the hardware available? | Owner statement; hardware inventory | UNVERIFIED |
| 7 | Is there a verified way to restore the factory state? | Documented restore path tested on a non-critical unit, or a source with a restore image | UNVERIFIED |
| 8 | Is root or shell access available after the method? | Observed on device only after approval | UNVERIFIED |
| 9 | Does the method change Wi-Fi, TLS or certificate behaviour? | Test on device | UNVERIFIED |
| 10 | Does the battery pose a risk under continuous charging? | H0 battery observations | UNVERIFIED |

## Decision

- **Current status:** no acceptable path identified. Device modification is **not** proposed.
- **Fallback** (plan §12): stop device modification; continue cloud and mobile work; offer manual USB image transfer, or a supported replacement display.
- **Next step:** complete H0, then research items 1–7 with sources recorded here, then ask the owner for a decision.

## Research leads — 29 October 2026 (community sources; UNVERIFIED)

Found by web search. These are leads only. None has been checked against a primary source, and none is a method for this device. Do not download or run anything from these pages. Any package needs a provenance check first (Principles above).

| Lead | Source | What it says | Why it matters |
|---|---|---|---|
| Community wiki, firmware-by-firmware table | [MobileRead Kindle Touch Hacking](https://wiki.mobileread.com/wiki/Kindle_Touch_Hacking) | 5.3.3 and 5.3.6 need a downgrade to 5.3.1 or 5.3.5 first. A manual method is noted for 5.3.7. The page predates 5.3.7.3. | The device is already on 5.3.7.3, so this downgrade path may not apply. It is also a downgrade, which carries risk. |
| Forum reports on the update path | MobileRead threads returned by search (for example [p=4551972](https://www.mobileread.com/forums/showthread.php?p=4551972)) | A device on 5.1.1 must be updated to 5.3.7.3 before the jailbreak works. One user could not use the update button. A second-hand quote attributes a staged update, 5.3.2.1 then 5.3.7.3, to Amazon's help page. | Not checked against Amazon's page. The staged route, if real, shows the update path is fragile. |
| Blog post on a 5.0.x–5.4.4.2 package | [bubbles.town](https://bubbles.town/entry/44771447) | Names a "K5 JailBreak" package containing `kindle-5.4-jailbreak.zip`. Says Amazon ended support in May. | Package name, hash and author are unknown. Not verified. |
| Community FAQ on updates | MobileRead wiki and threads (as above) | From 5.3.x, official updates overwrite the whole system. Simple extensions usually survive, but system-level changes may need reinstalling. | An automatic update could remove any change. Update behaviour must be checked before any change. |
| Reported KUAL error | MobileRead threads (as above) | Users report "not signed by an authorised developer" errors, and a DevCerts fix that is unconfirmed. | A known failure mode. Unresolved in the reports. |

### What the leads establish, and what they do not

- They agree that 5.3.7.3 is the target firmware and that community tools exist for it.
- They do **not** show a method verified for a device already on 5.3.7.3, which is this device's state.
- They do **not** document a recovery route. H1 item 7 stays open.
- The reports conflict on the update path. Treat each as unconfirmed.

### New items raised by the leads (add to the checklist)

11. Is automatic firmware update enabled, and could the device update itself over Wi-Fi? Find out on the device, without changing settings, before any network connection is made for H1.
12. Which exact package names, versions and hashes are being considered? Record them before any download, and reject anything from an unknown mirror.
13. Is an unsigned-code error expected? If so, is there a documented remedy from a source the owner accepts?

Status is unchanged: **no acceptable H1 path is identified, and device modification is not proposed.**
