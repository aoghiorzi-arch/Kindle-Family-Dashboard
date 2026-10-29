// Test harness: real handlers and real migration SQL, with node:sqlite standing in for D1.
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { D1Database, D1PreparedStatement, Env } from "../src/env.ts";
import { handle } from "../src/worker.ts";

export const MIGRATION = fileURLToPath(new URL("../../../infrastructure/cloudflare/migrations/0001_init.sql", import.meta.url));
export const ORIGIN = "https://family.test";

class SqliteStatement implements D1PreparedStatement {
  private readonly db: DatabaseSync;
  private readonly sql: string;
  private args: unknown[] = [];

  constructor(db: DatabaseSync, sql: string) {
    this.db = db;
    this.sql = sql;
  }

  bind(...values: unknown[]): D1PreparedStatement {
    for (const value of values) {
      // D1 rejects undefined and booleans; the handlers must never send them.
      if (value === undefined || typeof value === "boolean") throw new Error(`invalid bind value: ${typeof value}`);
    }
    this.args = values;
    return this;
  }

  async first<T>(): Promise<T | null> {
    const row = this.db.prepare(this.sql).get(...(this.args as never[]));
    return (row as T | undefined) ?? null;
  }

  async all<T>(): Promise<{ results: T[] }> {
    return { results: this.db.prepare(this.sql).all(...(this.args as never[])) as T[] };
  }

  async run(): Promise<{ meta: { changes: number } }> {
    const result = this.db.prepare(this.sql).run(...(this.args as never[]));
    return { meta: { changes: Number(result.changes) } };
  }
}

export function openDatabase(): DatabaseSync {
  const db = new DatabaseSync(":memory:");
  db.exec("PRAGMA foreign_keys = ON");
  db.exec(readFileSync(MIGRATION, "utf8"));
  return db;
}

export function makeEnv(db: DatabaseSync, environment = "local"): Env {
  const DB: D1Database = { prepare: (sql: string) => new SqliteStatement(db, sql) };
  return { DB, ENVIRONMENT: environment, PUBLIC_ORIGIN: ORIGIN };
}

export function seed(db: DatabaseSync, timezone = "Europe/London") {
  const stamp = "2026-10-01T00:00:00Z";
  db.prepare("INSERT INTO households (id, name, timezone, created_at) VALUES (?, ?, ?, ?)")
    .run("h1", "Household One", timezone, stamp);
  db.prepare("INSERT INTO households (id, name, timezone, created_at) VALUES (?, ?, ?, ?)")
    .run("h2", "Household Two", "Europe/London", stamp);
  const member = db.prepare("INSERT INTO members (id, household_id, display_name, role, created_at) VALUES (?, ?, ?, ?, ?)");
  member.run("a1", "h1", "Alex", "admin", stamp);
  member.run("m1", "h1", "Sam", "member", stamp);
  member.run("x1", "h2", "Other admin", "admin", stamp);
}

export interface Opts {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  cookie?: string;
  csrf?: string;
  origin?: string | null;
  rawBody?: string;
}

export function request(path: string, opts: Opts = {}): Request {
  const headers: Record<string, string> = { ...(opts.headers ?? {}) };
  let body: string | undefined = opts.rawBody;
  if (opts.body !== undefined) {
    body = JSON.stringify(opts.body);
    headers["Content-Type"] = "application/json";
  }
  if (opts.cookie) headers["Cookie"] = opts.cookie;
  if (opts.csrf) headers["X-CSRF-Token"] = opts.csrf;
  if (opts.origin === undefined ? opts.csrf !== undefined : opts.origin !== null) headers["Origin"] = opts.origin ?? ORIGIN;
  return new Request(`https://family.test${path}`, { method: opts.method ?? "GET", headers, body });
}

export async function signIn(env: Env, memberId: string, now?: Date): Promise<{ cookie: string; csrf: string }> {
  const login = await handle(request("/api/dev/login", { method: "POST", body: { memberId } }), env, now);
  const setCookie = login.headers.get("Set-Cookie") ?? "";
  const cookie = setCookie.split(";")[0];
  const me = await handle(request("/api/me", { cookie }), env, now);
  const body = (await me.json()) as { csrfToken: string };
  return { cookie, csrf: body.csrfToken };
}

export async function createDevice(
  env: Env,
  session: { cookie: string; csrf: string },
  kind: "display" | "shortcut",
  name = "Test device",
): Promise<{ id: string; token: string }> {
  const res = await handle(
    request("/api/admin/devices", { method: "POST", body: { name, kind }, cookie: session.cookie, csrf: session.csrf }),
    env,
  );
  const body = (await res.json()) as { device: { id: string }; token: string };
  return { id: body.device.id, token: body.token };
}

export function bearer(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

// Validator for the shared contract (packages/contracts). Same file the device and simulator use.
import Ajv2020 from "ajv/dist/2020.js";
const CONTRACT = fileURLToPath(new URL("../../../packages/contracts/kindle-snapshot.v1.schema.json", import.meta.url));
const ajv = new Ajv2020({ allErrors: true, strict: false });
export const validateSnapshotSchema = ajv.compile(JSON.parse(readFileSync(CONTRACT, "utf8")));
