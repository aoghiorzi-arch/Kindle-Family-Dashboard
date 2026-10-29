// Minimal structural types for the bindings the Worker uses. The real D1Database satisfies these;
// tests supply an in-memory implementation with the same surface.

export interface D1Result<T> {
  results: T[];
}

export interface D1PreparedStatement {
  bind(...values: unknown[]): D1PreparedStatement;
  first<T = Record<string, unknown>>(): Promise<T | null>;
  all<T = Record<string, unknown>>(): Promise<D1Result<T>>;
  run(): Promise<{ meta: { changes: number } }>;
}

export interface D1Database {
  prepare(sql: string): D1PreparedStatement;
}

export interface Env {
  DB: D1Database;
  // "local" enables the dev sign-in route. Any other value (or unset) fails closed.
  ENVIRONMENT?: string;
  // Exact origin of the family web app, for CSRF checks on writes, for example https://family.example
  PUBLIC_ORIGIN: string;
  // Cloudflare Access (production sign-in). When ACCESS_TEAM_DOMAIN and ACCESS_AUD are set, members are identified by Access.
  // ACCESS_TEAM_DOMAIN is for example family.cloudflareaccess.com; ACCESS_AUD is the application's audience tag.
  ACCESS_TEAM_DOMAIN?: string;
  ACCESS_AUD?: string;
  // Secret used to derive CSRF tokens in Access mode. Set with `wrangler secret put CSRF_SECRET`.
  CSRF_SECRET?: string;
  // Integrations (Phase 5). Feed addresses are secrets. Calendar and news serve one household (HOUSEHOLD_ID) for now.
  CALENDAR_FEED_URL?: string;
  HOUSEHOLD_ID?: string;
  // JSON array of up to three https RSS or Atom URLs.
  NEWS_FEED_URLS?: string;
}
