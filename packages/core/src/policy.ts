// Refresh and rate-limit rules for external providers. Shared by the scheduled job and the tests.

export type Provider = "weather" | "calendar" | "news";

const MINUTE = 60_000;

export const POLICY: Record<Provider, { maxAgeMs: number; minIntervalMs: number }> = {
  weather: { maxAgeMs: 30 * MINUTE, minIntervalMs: 15 * MINUTE },
  calendar: { maxAgeMs: 15 * MINUTE, minIntervalMs: 15 * MINUTE },
  news: { maxAgeMs: 60 * MINUTE, minIntervalMs: 30 * MINUTE },
};

export const MAX_BACKOFF_MS = 60 * MINUTE;

export interface CacheState {
  fetchedAt: string | null; // last successful fetch, UTC ISO
  nextAttemptAt: string | null; // earliest next attempt, UTC ISO
}

// A new attempt is allowed when there is no fresh copy and the rate limit has passed.
export function shouldAttempt(state: CacheState | null, provider: Provider, now: Date): boolean {
  if (!state) return true;
  if (state.nextAttemptAt && now.getTime() < Date.parse(state.nextAttemptAt)) return false;
  if (state.fetchedAt && now.getTime() - Date.parse(state.fetchedAt) < POLICY[provider].maxAgeMs) return false;
  return true;
}

// After a failure, wait the minimum interval, doubling for each consecutive failure, capped at one hour.
export function nextAttemptAfterFailure(provider: Provider, failures: number, now: Date): Date {
  const wait = Math.min(POLICY[provider].minIntervalMs * 2 ** Math.max(0, failures - 1), MAX_BACKOFF_MS);
  return new Date(now.getTime() + wait);
}

export function nextAttemptAfterSuccess(provider: Provider, now: Date): Date {
  return new Date(now.getTime() + POLICY[provider].minIntervalMs);
}
