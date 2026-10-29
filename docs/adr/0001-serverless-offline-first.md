# ADR 0001 — Serverless, offline-first architecture

- **Status:** Accepted for decisions D1–D6 at their stated defaults (owner reply, 29 October 2026). The phase sequence is approved (owner reply, 29 October 2026).
- **Date:** 29 October 2026
- **Baseline:** commit `9a0bed5` on `claude/funny-hamilton-pfuhsz`
- **Source:** [`SERVERLESS_MASTER_PLAN.md`](../SERVERLESS_MASTER_PLAN.md) §2–§3

## Context

The repository currently implements a local-only Family Hub prototype: a stdlib Python HTTP server, SQLite storage, server-rendered 600×800 PNGs, and a host-only Python display client (see [`../PHASE0_AUDIT.md`](../PHASE0_AUDIT.md)). Earlier planning documents ([`../../MASTER_PLAN_V2.md`](../../MASTER_PLAN_V2.md), [`../ORIGINAL_MASTER_PLAN.md`](../ORIGINAL_MASTER_PLAN.md)) assumed a Hostinger-hosted backend. The new master plan rules out any self-administered server, VPS, Raspberry Pi or required always-on Mac, and proposes managed Cloudflare services instead.

The Kindle Touch (D01200, firmware 5.3.7.3) is unverified for HTTPS, clock, suspend/wake, storage and any modification path. The display must keep working from cache when Wi-Fi or the cloud is unavailable.

## Decision (proposed)

1. **Hosting:** Cloudflare Pages (family web app), Cloudflare Workers (API, validation, scheduled caching, adapters), Cloudflare D1 (structured data), Scheduled Workers (provider fetches with rate limits).
2. **Kindle contract:** a versioned, minimal, read-only, device-scoped JSON snapshot. The cloud precomputes normalised data. The Kindle never calls third-party APIs and never receives auth material, provider tokens or edit endpoints.
3. **Kindle client:** fetch snapshot → validate → write atomically to a local cache → render locally → keep last known-good data. Rendering on the device is proposed, not proven; a server-rendered PNG path may be kept as a fallback only if H3 and H2 fail in a way that justifies it (decision D4 below).
4. **Offline-first:** cached display on reboot before any network access; stale data marked explicitly; never blank because of a provider or network failure.
5. **Hardware gates stay in force:** H0 (non-invasive readiness), H1 (documented recovery route, explicit consent), H2 (renderer proof), H3 (verified HTTPS from device). No device modification is authorised by accepting this ADR.
6. **Phase-by-phase migration:** existing Python logic is preserved and ported incrementally; no wholesale rewrite before the contracts and tests exist.

## Consequences

- Positive: no server for the family to administer; managed backups and TLS; the Kindle needs only a small read-only client.
- Negative: vendor lock-in to Cloudflare; quota and pricing changes must be monitored; a runtime change (see D1) means some existing Python code must be re-implemented or run through a different path.
- Neutral: the existing 214-test suite remains the regression oracle during migration.

## Decisions (D1–D6 accepted at defaults)

D1 spike (29 October 2026, partly complete): the TypeScript default stands. Two of the three Python dependencies are unverified in Pyodide, and the ICS subprocess isolation has to be rebuilt in any runtime. See [`../D1-runtime-spike.md`](../D1-runtime-spike.md).

| ID | Question | Default if not decided | Notes |
|---|---|---|---|
| D1 | Worker runtime: TypeScript, or Python Workers? | **Accepted:** TypeScript for the Worker; port logic into `packages/core` | Pillow, icalendar and cryptography are Python packages; Python Workers support for them is **UNVERIFIED**. |
| D2 | Authentication provider | **Accepted: Cloudflare Access** with email one-time codes (owner choice). Device and Shortcut credentials stay with the Worker. See [`../SIGN_IN_ACCESS.md`](../SIGN_IN_ACCESS.md). | Dashboard setup pending. |
| D3 | Calendar source | Read-only private iCal feed behind an adapter | Feed URLs are bearer secrets; store only as Worker secrets. |
| D4 | On-device render or server PNG | On-device render from JSON, proven at H2 | Server PNG is the fallback if H2 fails. |
| D5 | Weather, news and verse providers | Pending | Licensing and attribution must be checked first. |
| D6 | Hostname | Cloudflare subdomain | Custom domain later. |

## Rejected alternatives

- **Keep the Python server on a Hostinger plan:** conflicts with the new no-server requirement; retained only as the local prototype and test oracle.
- **Direct Kindle calls to third-party APIs:** rejected. The Kindle browser and TLS stack are unverified, and every provider credential would sit on the device.
- **Disabling certificate validation for old TLS:** rejected in every case. The plan requires a verified HTTPS path or a USB or manual fallback.
