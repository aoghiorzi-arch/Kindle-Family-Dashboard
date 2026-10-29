-- Phase 3 foundation schema (Cloudflare D1 / SQLite).
-- Every family-owned row carries household_id; every query must filter on it.
-- Secrets are stored only as SHA-256 hashes (session and API tokens).

CREATE TABLE households (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 60),
  timezone TEXT NOT NULL DEFAULT 'Europe/London' CHECK (length(timezone) BETWEEN 1 AND 64),
  created_at TEXT NOT NULL
);

CREATE TABLE members (
  id TEXT PRIMARY KEY,
  household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
  display_name TEXT NOT NULL CHECK (length(display_name) BETWEEN 1 AND 60),
  role TEXT NOT NULL CHECK (role IN ('admin', 'member')),
  created_at TEXT NOT NULL
);
CREATE INDEX members_household ON members (household_id);

CREATE TABLE sessions (
  token_hash TEXT PRIMARY KEY CHECK (length(token_hash) = 64),
  member_id TEXT NOT NULL REFERENCES members(id) ON DELETE CASCADE,
  csrf_token TEXT NOT NULL CHECK (length(csrf_token) >= 32),
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX sessions_member ON sessions (member_id);

CREATE TABLE devices (
  id TEXT PRIMARY KEY,
  household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
  name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 60),
  kind TEXT NOT NULL CHECK (kind IN ('display', 'shortcut')),
  created_at TEXT NOT NULL,
  revoked_at TEXT
);
CREATE INDEX devices_household ON devices (household_id);

CREATE TABLE api_tokens (
  token_hash TEXT PRIMARY KEY CHECK (length(token_hash) = 64),
  device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
  scope TEXT NOT NULL CHECK (scope IN ('snapshot:read', 'shopping:add')),
  created_at TEXT NOT NULL,
  revoked_at TEXT
);
CREATE INDEX api_tokens_device ON api_tokens (device_id);

CREATE TABLE shopping_items (
  id TEXT PRIMARY KEY,
  household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
  title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 60),
  done INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0, 1)),
  position INTEGER NOT NULL CHECK (position >= 0),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  created_by TEXT REFERENCES members(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX shopping_household_position ON shopping_items (household_id, position);
