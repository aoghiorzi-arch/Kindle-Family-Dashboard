# Phase 5 — integrations and caching

**Date:** 29 October 2026 · **Status:** built and tested locally. **Not deployed.** Provider choices are set as defaults, but **licensing for weather and news must be confirmed by the owner before use** (see the table below).
**Gate (plan §9):** provider failure does not blank the dashboard; rate limits respected; all content has correct timezone and source attribution.

## What was built

| Module | Where | What it does |
|---|---|---|
| Sunrise and sunset | `packages/core/src/sun.ts` | Ported from `app/solar.py`, with sunrise added. Times are rendered in the household zone. |
| Weather | `packages/core/src/weather.ts`, `apps/api/src/scheduled.ts` | Open-Meteo current conditions, WMO code summaries, attribution carried into the snapshot. |
| Calendar | `packages/core/src/calendar.ts` | iCalendar expansion with `ical.js`: recurrence, exclusions, moved and cancelled occurrences, all-day events, and private events masked as "Busy" before storage. |
| News | `packages/core/src/news.ts` | RSS and Atom titles only, up to three headlines, with the source name as attribution. No excerpts are stored. |
| Daily thought | `packages/core/src/verse.ts` | Same index as the Python version. KJV text carried over, not yet checked against a printed Bible. |
| Refresh policy | `packages/core/src/policy.ts` | Maximum age, minimum interval between attempts, exponential backoff capped at one hour. |
| Cache | `infrastructure/cloudflare/migrations/0002_integrations.sql` | `provider_cache`: last good payload, timestamps, failure count and a short error code. |
| Scheduled job | `apps/api/src/scheduled.ts`, `worker.ts` | Runs every 15 minutes. The only code that calls providers. |
| Bounded fetch | `apps/api/src/feeds.ts` | https only, no credentials in the address, no redirects, a time limit and a size limit. |
| Location | `GET` and `PUT /api/admin/household/location`, Settings form | Admin sets latitude and longitude for sunrise, sunset and weather. Members do not see the form. |

The display snapshot reads only the local database. It never calls a provider.

## Licensing and attribution

| Source | Used for | Terms (to verify) | Attribution shown | Status |
|---|---|---|---|---|
| **Open-Meteo** `api.open-meteo.com` | Current temperature and conditions | Free API: **non-commercial use only**, under 10,000 calls a day. Data under CC BY 4.0. No key. ([terms](https://open-meteo.com/en/terms), [pricing](https://open-meteo.com/en/pricing)) | "Weather data by Open-Meteo.com (CC BY 4.0)" in the snapshot and on the phone Home screen | **Owner to confirm** that a private household display counts as non-commercial use. |
| **Family calendar feed** (iCalendar, operator-supplied secret) | Today's events | Owned by the family. The feed address is a bearer secret. | None required | The operator supplies the address. Private titles are masked before storage. |
| **News feeds** (RSS or Atom, operator-supplied, up to three) | Headline titles | **Depends on the chosen feed.** No default feed is configured. | The feed's channel title is shown with each headline | **Owner to choose feeds and confirm their terms.** Only titles are stored. |
| **Daily thought** (KJV, public domain) | Daily thought | KJV is public domain. Text not yet checked against a printed Bible. | Reference shown on the display | Check before use, as the Python version already notes. |
| **ical.js** | Calendar expansion (server-side) | MPL-2.0 | Not displayed | Used server-side only, with no distribution of modified source. |
| **fast-xml-parser** | News parsing (server-side) | MIT | Not displayed | — |

## Gate evidence

| Gate item | Evidence |
|---|---|
| Provider failure does not blank the dashboard | Test `provider outages do not blank the dashboard…`: shopping and the last good weather remain after every provider fails. Test `with no providers configured…`: explicit empty states, still valid. |
| Rate limits respected | Test `rate limits hold…`: repeated runs make one call. Test `failures back off…`: no retry until the wait has passed. The one-hour cap is a core test. |
| Failures do not leak detail | Test `a provider failure is recorded as a short code…`. The live check recorded `unreachable`, with no URL or response body. |
| Timezone correct | Tests: the snapshot date follows the household zone (Tokyo); sun times are in the household zone; floating calendar times are read as household local time; all-day events start at local midnight. |
| Attribution present | The attribution text names the source. Snapshot tests check `weather.attribution`, `reflection.attribution`, and news `source`. |
| Privacy in the cache | Test `private calendar titles are masked before they are stored`. Test `a household's cache is not visible to another household's display`. |
| Bounds | Tests: redirects refused; oversized responses refused; non-https and credentialed calendar addresses refused without a network call; news limited to three feeds. |
| Sunrise and sunset accuracy | Six locations compared with the independent library `astral` 3.2 (run once, outside the repository) and with the Python implementation. Agreement within one minute. |

Results: `packages/core` **35 tests pass**; `apps/api` **66 tests pass**; Python prototype **227 tests pass**; browser checks **26 pass**.

**Local Worker run:** migrations applied, the Worker started with the new dependencies, and the scheduled job triggered. The sandbox could not reach the providers, so each one recorded `unreachable`, and the snapshot still built with sunrise and sunset from the stored location.

## Not verified

- **Live weather response.** The sandbox cannot reach `api.open-meteo.com`, so the parser assumes the response shape from Open-Meteo's documented `current` block. Check one live response before relying on it.
- **Verse text.** Not checked against a printed Bible.
- **Sunrise and sunset in production.** Agreement with astral and Python was checked, but not with a physical reference for these dates.
- **Real calendar and news feeds.** Tested with synthetic fixtures only.

## Gaps and open decisions

1. **D5 (providers) is not fully decided.** Weather defaults to Open-Meteo. News has no default feed. The owner must confirm the weather terms and choose news sources.
2. **Calendar data is not encrypted at rest in D1.** The Python prototype encrypted feed text. The Worker stores masked event titles and times unencrypted. Decide whether that is acceptable, or add encryption before the calendar goes live.
3. **Calendar and news serve one household** (`HOUSEHOLD_ID`). Multi-household integrations need per-household configuration.
4. **Outbound addresses are not pinned to an IP address.** Workers cannot pin resolved addresses. Feed addresses come from operator secrets, not from users. Acceptable for a private family deployment; revisit before any wider use.
5. **Calendar text is re-read every 15 minutes** over a seven-day window. Very large feeds hit the two-megabyte limit and are refused with `too_large`.
6. **Scheduled job timing** under Cloudflare's real cron is not measured. The local trigger ran once.
7. **Moved occurrences** are applied from the feed's own override records. A series with an occurrence in an unknown time zone is still skipped and counted.

## Rollback

Revert the changes to `packages/core/src` (sun, weather, news, calendar, verse, policy, snapshot), `apps/api/src/scheduled.ts` and `feeds.ts`, the `[triggers]` block in `wrangler.toml`, and the location route. Drop `provider_cache` and the two location columns with a new migration. The snapshot then falls back to shopping-only content.
