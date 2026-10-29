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
  // Integrations (Phase 5). Feed addresses are secrets. Calendar and news serve one household (HOUSEHOLD_ID) for now.
  CALENDAR_FEED_URL?: string;
  HOUSEHOLD_ID?: string;
  // JSON array of up to three https RSS or Atom URLs.
  NEWS_FEED_URLS?: string;
}
