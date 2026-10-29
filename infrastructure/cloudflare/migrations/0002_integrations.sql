-- Phase 5: household location (for sunrise, sunset and weather) and a cache of external provider data.
-- Displays read only this cache. Only the scheduled job talks to providers.

ALTER TABLE households ADD COLUMN latitude REAL CHECK (latitude IS NULL OR (latitude BETWEEN -90 AND 90));
ALTER TABLE households ADD COLUMN longitude REAL CHECK (longitude IS NULL OR (longitude BETWEEN -180 AND 180));

CREATE TABLE provider_cache (
  household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
  provider TEXT NOT NULL CHECK (provider IN ('weather', 'calendar', 'news')),
  payload TEXT,                                   -- JSON of the last good data; NULL until the first success
  fetched_at TEXT,                                -- UTC ISO of the last good data
  next_attempt_at TEXT,                           -- earliest next provider call (rate limit and backoff)
  failures INTEGER NOT NULL DEFAULT 0 CHECK (failures >= 0),
  last_error TEXT,                                -- short code only: never a URL, response body or secret
  PRIMARY KEY (household_id, provider)
);
