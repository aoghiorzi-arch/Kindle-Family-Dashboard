// The scheduled job: the only code that calls external providers. Displays read the cache it writes.
import type { Env } from "./env.ts";
import { boundedJson, boundedText, ProviderError, type FetchLike } from "./feeds.ts";
import {
  expandCalendar,
  MAX_FEED_BYTES,
  nextAttemptAfterFailure,
  nextAttemptAfterSuccess,
  openMeteoUrl,
  parseHeadlines,
  parseOpenMeteoCurrent,
  shouldAttempt,
  type CalendarEvent,
  type CacheState,
  type Headline,
  type Provider,
  limitHeadlines,
} from "../../../packages/core/src/index.ts";

export const PROVIDER_TIMEOUT_MS = 8000;
export const NEWS_MAX_BYTES = 512_000;
export const CALENDAR_WINDOW_DAYS = 7;
export const MAX_NEWS_FEEDS = 3;

interface Household {
  id: string;
  timezone: string;
  latitude: number | null;
  longitude: number | null;
}

interface CacheRow {
  payload: string | null;
  fetched_at: string | null;
  next_attempt_at: string | null;
  failures: number;
}

export interface JobResult {
  attempted: number;
  succeeded: number;
  failed: number;
}

async function readCache(env: Env, householdId: string, provider: Provider): Promise<CacheRow | null> {
  return env.DB.prepare("SELECT payload, fetched_at, next_attempt_at, failures FROM provider_cache WHERE household_id = ? AND provider = ?")
    .bind(householdId, provider)
    .first<CacheRow>();
}

// Records a success or a failure. Failures keep the last good payload and back off.
async function record(env: Env, householdId: string, provider: Provider, now: Date, outcome: { payload?: unknown; error?: string }): Promise<void> {
  const current = await readCache(env, householdId, provider);
  if (outcome.error === undefined) {
    await env.DB.prepare(
      `INSERT INTO provider_cache (household_id, provider, payload, fetched_at, next_attempt_at, failures, last_error)
       VALUES (?, ?, ?, ?, ?, 0, NULL)
       ON CONFLICT (household_id, provider) DO UPDATE SET
         payload = excluded.payload, fetched_at = excluded.fetched_at, next_attempt_at = excluded.next_attempt_at,
         failures = 0, last_error = NULL`,
    )
      .bind(householdId, provider, JSON.stringify(outcome.payload), now.toISOString(), nextAttemptAfterSuccess(provider, now).toISOString())
      .run();
    return;
  }
  const failures = (current?.failures ?? 0) + 1;
  await env.DB.prepare(
    `INSERT INTO provider_cache (household_id, provider, payload, fetched_at, next_attempt_at, failures, last_error)
     VALUES (?, ?, NULL, NULL, ?, ?, ?)
     ON CONFLICT (household_id, provider) DO UPDATE SET
       next_attempt_at = excluded.next_attempt_at, failures = excluded.failures, last_error = excluded.last_error`,
  )
    .bind(householdId, provider, nextAttemptAfterFailure(provider, failures, now).toISOString(), failures, outcome.error)
    .run();
}

async function refreshProvider(
  env: Env,
  household: Household,
  provider: Provider,
  now: Date,
  job: () => Promise<unknown>,
  result: JobResult,
): Promise<void> {
  const current = await readCache(env, household.id, provider);
  const state: CacheState | null = current ? { fetchedAt: current.fetched_at, nextAttemptAt: current.next_attempt_at } : null;
  if (!shouldAttempt(state, provider, now)) return;
  result.attempted += 1;
  try {
    await record(env, household.id, provider, now, { payload: await job() });
    result.succeeded += 1;
  } catch (error) {
    const code = error instanceof ProviderError ? error.code : "failed";
    await record(env, household.id, provider, now, { error: code });
    result.failed += 1;
  }
}

async function weatherJob(env: Env, household: Household, fetcher: FetchLike): Promise<unknown> {
  if (household.latitude === null || household.longitude === null) throw new ProviderError("no_location");
  const body = await boundedJson(openMeteoUrl(household.latitude, household.longitude, household.timezone), fetcher, 64_000, PROVIDER_TIMEOUT_MS);
  return parseOpenMeteoCurrent(body);
}

async function calendarJob(env: Env, household: Household, now: Date, fetcher: FetchLike): Promise<unknown> {
  if (!env.CALENDAR_FEED_URL) throw new ProviderError("not_configured");
  const text = await boundedText(env.CALENDAR_FEED_URL, fetcher, MAX_FEED_BYTES, PROVIDER_TIMEOUT_MS);
  const to = new Date(now.getTime() + CALENDAR_WINDOW_DAYS * 86_400_000);
  const from = new Date(now.getTime() - 86_400_000);
  try {
    const { events, skipped } = expandCalendar(text, from, to, household.timezone);
    return { events, skipped };
  } catch {
    throw new ProviderError("bad_response");
  }
}

async function newsJob(env: Env, fetcher: FetchLike): Promise<unknown> {
  const urls = parseFeedList(env.NEWS_FEED_URLS);
  if (urls.length === 0) throw new ProviderError("not_configured");
  const lists: Headline[][] = [];
  for (const url of urls) {
    const xml = await boundedText(url, fetcher, NEWS_MAX_BYTES, PROVIDER_TIMEOUT_MS);
    try {
      lists.push(parseHeadlines(xml));
    } catch {
      throw new ProviderError("bad_response");
    }
  }
  return { headlines: limitHeadlines(lists) };
}

export function parseFeedList(value: string | undefined): string[] {
  if (!value) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error("NEWS_FEED_URLS must be a JSON array of https URLs");
  }
  if (!Array.isArray(parsed) || parsed.some((u) => typeof u !== "string")) {
    throw new Error("NEWS_FEED_URLS must be a JSON array of https URLs");
  }
  return parsed.slice(0, MAX_NEWS_FEEDS) as string[];
}

// Runs every provider that is due. Safe to call often: the rate limits decide what actually runs.
export async function runScheduled(env: Env, now: Date, fetcher: FetchLike = fetch): Promise<JobResult> {
  const result: JobResult = { attempted: 0, succeeded: 0, failed: 0 };
  const { results: households } = await env.DB.prepare(
    "SELECT id, timezone, latitude, longitude FROM households",
  ).all<Household>();

  for (const household of households) {
    if (household.latitude !== null && household.longitude !== null) {
      await refreshProvider(env, household, "weather", now, () => weatherJob(env, household, fetcher), result);
    }
    if (env.CALENDAR_FEED_URL && env.HOUSEHOLD_ID === household.id) {
      await refreshProvider(env, household, "calendar", now, () => calendarJob(env, household, now, fetcher), result);
    }
    if (env.NEWS_FEED_URLS && env.HOUSEHOLD_ID === household.id) {
      await refreshProvider(env, household, "news", now, () => newsJob(env, fetcher), result);
    }
  }
  return result;
}

// Reads a good cached payload, or null. Used by the snapshot builder; never calls a provider.
export async function cachedPayload<T>(env: Env, householdId: string, provider: Provider): Promise<{ data: T; fetchedAt: string } | null> {
  const row = await readCache(env, householdId, provider);
  if (!row || row.payload === null || row.fetched_at === null) return null;
  return { data: JSON.parse(row.payload) as T, fetchedAt: row.fetched_at };
}

export type CachedCalendar = { events: CalendarEvent[]; skipped: number };
export type CachedNews = { headlines: Headline[] };
export type CachedWeather = { temperatureC: number; summary: string; observedAt: string };
