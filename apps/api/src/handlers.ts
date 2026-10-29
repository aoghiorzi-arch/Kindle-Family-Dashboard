// Route handlers. Each one resolves identity first and filters every query by household_id.
import type { Env } from "./env.ts";
import { HttpError, json, readJson } from "./http.ts";
import {
  clearSessionCookie,
  createSession,
  requireCsrf,
  requireDevice,
  requireSession,
  sessionCookie,
  type MemberSession,
} from "./auth.ts";
import { cachedPayload, type CachedCalendar, type CachedNews, type CachedWeather } from "./scheduled.ts";
import {
  localDate,
  thoughtForDate,
  WEATHER_ATTRIBUTION,
  buildSnapshot,
  generateApiToken,
  LIST_LIMIT,
  parseOptionalBoolean,
  parseOptionalPosition,
  parseTitle,
  parseVersion,
  sha256Hex,
  ValidationError,
} from "../../../packages/core/src/index.ts";

interface ItemRow {
  id: string;
  title: string;
  done: number;
  position: number;
  version: number;
}

function toItem(row: ItemRow) {
  return { id: row.id, title: row.title, done: row.done === 1, position: row.position, version: row.version };
}

// Turns a parser's ValidationError into a 400 response; other errors propagate unchanged.
function validate<T>(parse: () => T): T {
  try {
    return parse();
  } catch (error) {
    if (error instanceof ValidationError) throw new HttpError(400, "validation_failed", error.message);
    throw error;
  }
}

function parseId(value: string): string {
  if (!/^[0-9a-f-]{36}$/.test(value)) throw new HttpError(404, "not_found", "Item not found");
  return value;
}

// ---- Browser session -------------------------------------------------------

export async function me(request: Request, env: Env, now: Date): Promise<Response> {
  const session = await requireSession(request, env, now);
  return json({
    memberId: session.memberId,
    displayName: session.displayName,
    householdId: session.householdId,
    role: session.role,
    csrfToken: session.csrfToken,
  });
}

// Local development only. Production has no sign-in route until a provider is chosen (ADR D2).
export async function devLogin(request: Request, env: Env, now: Date): Promise<Response> {
  if (env.ENVIRONMENT !== "local") throw new HttpError(404, "not_found", "Not found");
  const body = await readJson(request);
  const memberId = typeof body.memberId === "string" ? body.memberId : "";
  const member = await env.DB.prepare("SELECT id, role FROM members WHERE id = ?")
    .bind(memberId)
    .first<{ id: string; role: string }>();
  if (!member) throw new HttpError(401, "unauthenticated", "Sign in failed");
  const token = await createSession(env, member.id, now);
  return json({ memberId: member.id, role: member.role }, 200, { "Set-Cookie": sessionCookie(token) });
}

export async function logout(request: Request, env: Env, now: Date): Promise<Response> {
  const session = await requireSession(request, env, now);
  requireCsrf(request, env, session);
  await env.DB.prepare("DELETE FROM sessions WHERE member_id = ? AND csrf_token = ?")
    .bind(session.memberId, session.csrfToken)
    .run();
  return json({ ok: true }, 200, { "Set-Cookie": clearSessionCookie() });
}

// ---- Shopping --------------------------------------------------------------

export async function listShopping(request: Request, env: Env, now: Date): Promise<Response> {
  const session = await requireSession(request, env, now);
  const { results } = await env.DB.prepare(
    `SELECT id, title, done, position, version FROM shopping_items
      WHERE household_id = ? ORDER BY position, created_at LIMIT ?`,
  )
    .bind(session.householdId, LIST_LIMIT)
    .all<ItemRow>();
  return json({ items: results.map(toItem) });
}

// Writers: a signed-in browser (with CSRF) or a Shortcut token scoped to shopping:add.
interface Writer {
  householdId: string;
  memberId: string | null;
}

async function resolveWriter(request: Request, env: Env, now: Date): Promise<Writer> {
  const hasBearer = (request.headers.get("Authorization") ?? "").startsWith("Bearer ");
  if (hasBearer) {
    const device = await requireDevice(request, env, ["shopping:add"]);
    return { householdId: device.householdId, memberId: null };
  }
  const session: MemberSession = await requireSession(request, env, now);
  requireCsrf(request, env, session);
  return { householdId: session.householdId, memberId: session.memberId };
}

export async function createItem(request: Request, env: Env, now: Date): Promise<Response> {
  const writer = await resolveWriter(request, env, now);
  const body = await readJson(request);
  const title = validate(() => parseTitle(body.title));
  const id = crypto.randomUUID();
  const stamp = now.toISOString();
  // One statement: the position is computed and the row inserted atomically.
  await env.DB.prepare(
    `INSERT INTO shopping_items (id, household_id, title, done, position, version, created_by, created_at, updated_at)
     SELECT ?, ?, ?, 0, COALESCE(MAX(position), -1) + 1, 1, ?, ?, ?
       FROM shopping_items WHERE household_id = ?`,
  )
    .bind(id, writer.householdId, title, writer.memberId, stamp, stamp, writer.householdId)
    .run();
  const row = await env.DB.prepare(
    "SELECT id, title, done, position, version FROM shopping_items WHERE id = ? AND household_id = ?",
  )
    .bind(id, writer.householdId)
    .first<ItemRow>();
  return json({ item: toItem(row!) }, 201);
}

export async function updateItem(request: Request, env: Env, now: Date, rawId: string): Promise<Response> {
  const session = await requireSession(request, env, now);
  requireCsrf(request, env, session);
  const id = parseId(rawId);
  const body = await readJson(request);
  const version = validate(() => parseVersion(body.version));
  const title = validate(() => (body.title === undefined ? undefined : parseTitle(body.title)));
  const done = validate(() => parseOptionalBoolean(body.done, "done"));
  const position = validate(() => parseOptionalPosition(body.position));
  if (title === undefined && done === undefined && position === undefined) {
    throw new HttpError(400, "validation_failed", "Nothing to change");
  }
  // Conditional update: succeeds only if the caller saw the current version.
  const result = await env.DB.prepare(
    `UPDATE shopping_items
        SET title = COALESCE(?, title), done = COALESCE(?, done), position = COALESCE(?, position),
            version = version + 1, updated_at = ?
      WHERE id = ? AND household_id = ? AND version = ?`,
  )
    .bind(
      title ?? null,
      done === undefined ? null : done ? 1 : 0,
      position ?? null,
      now.toISOString(),
      id,
      session.householdId,
      version,
    )
    .run();
  const current = await env.DB.prepare(
    "SELECT id, title, done, position, version FROM shopping_items WHERE id = ? AND household_id = ?",
  )
    .bind(id, session.householdId)
    .first<ItemRow>();
  if (!current) throw new HttpError(404, "not_found", "Item not found");
  if (result.meta.changes === 0) {
    return json({ error: { code: "conflict", message: "Item changed; reload and retry", current: toItem(current) } }, 409);
  }
  return json({ item: toItem(current) });
}

export async function deleteItem(request: Request, env: Env, now: Date, rawId: string, url: URL): Promise<Response> {
  const session = await requireSession(request, env, now);
  requireCsrf(request, env, session);
  const id = parseId(rawId);
  const version = validate(() => parseVersion(Number(url.searchParams.get("version"))));
  const result = await env.DB.prepare(
    "DELETE FROM shopping_items WHERE id = ? AND household_id = ? AND version = ?",
  )
    .bind(id, session.householdId, version)
    .run();
  if (result.meta.changes === 1) return json({ ok: true });
  const exists = await env.DB.prepare("SELECT 1 AS found FROM shopping_items WHERE id = ? AND household_id = ?")
    .bind(id, session.householdId)
    .first();
  if (!exists) throw new HttpError(404, "not_found", "Item not found");
  throw new HttpError(409, "conflict", "Item changed; reload and retry");
}

// ---- Device snapshot -------------------------------------------------------

// The same snapshot the Kindle receives, built for the household behind a credential.
// Reads only the local database. Provider data comes from the cache the scheduled job maintains.
async function householdSnapshot(env: Env, householdId: string, now: Date): Promise<Record<string, unknown>> {
  const household = await env.DB.prepare("SELECT timezone, latitude, longitude FROM households WHERE id = ?")
    .bind(householdId)
    .first<{ timezone: string; latitude: number | null; longitude: number | null }>();
  if (!household) throw new HttpError(404, "not_found", "Household not found");
  const { results } = await env.DB.prepare(
    "SELECT title FROM shopping_items WHERE household_id = ? AND done = 0 ORDER BY position, created_at",
  )
    .bind(householdId)
    .all<{ title: string }>();

  const weather = await cachedPayload<CachedWeather>(env, householdId, "weather");
  const calendar = await cachedPayload<CachedCalendar>(env, householdId, "calendar");
  const news = await cachedPayload<CachedNews>(env, householdId, "news");
  const thought = await thoughtForDate(localDate(now, household.timezone));

  return buildSnapshot({
    now,
    timezone: household.timezone,
    unchecked: results,
    location: household.latitude !== null && household.longitude !== null
      ? { latitude: household.latitude, longitude: household.longitude }
      : null,
    weather: weather
      ? { temperatureC: weather.data.temperatureC, summary: weather.data.summary, fetchedAt: weather.fetchedAt, attribution: WEATHER_ATTRIBUTION }
      : null,
    events: calendar?.data.events ?? [],
    news: news?.data.headlines ?? [],
    thought,
  });
}

function snapshotResponse(request: Request, snapshot: Record<string, unknown>): Response {
  const etag = `"${snapshot.revision as string}"`;
  if (request.headers.get("If-None-Match") === etag) {
    return new Response(null, { status: 304, headers: { ETag: etag, "Cache-Control": "no-store" } });
  }
  return json(snapshot, 200, { ETag: etag });
}

export async function deviceSnapshot(request: Request, env: Env, now: Date): Promise<Response> {
  const device = await requireDevice(request, env, ["snapshot:read"]);
  return snapshotResponse(request, await householdSnapshot(env, device.householdId, now));
}

// What the Kindle would show right now, for the phone's Home preview.
export async function snapshotPreview(request: Request, env: Env, now: Date): Promise<Response> {
  const session = await requireSession(request, env, now);
  return json(await householdSnapshot(env, session.householdId, now));
}

// ---- Admin: device credentials ---------------------------------------------

export async function listDevices(request: Request, env: Env, now: Date): Promise<Response> {
  const session = await requireSession(request, env, now);
  if (session.role !== "admin") throw new HttpError(403, "forbidden", "Admin access required");
  const { results } = await env.DB.prepare(
    `SELECT id, name, kind, created_at, revoked_at FROM devices
      WHERE household_id = ? ORDER BY created_at`,
  )
    .bind(session.householdId)
    .all<{ id: string; name: string; kind: string; created_at: string; revoked_at: string | null }>();
  return json({
    devices: results.map((d) => ({
      id: d.id,
      name: d.name,
      kind: d.kind,
      createdAt: d.created_at,
      active: d.revoked_at === null,
    })),
  });
}

const KIND_SCOPE = { display: "snapshot:read", shortcut: "shopping:add" } as const;

async function requireAdmin(request: Request, env: Env, now: Date): Promise<MemberSession> {
  const session = await requireSession(request, env, now);
  requireCsrf(request, env, session);
  if (session.role !== "admin") throw new HttpError(403, "forbidden", "Admin access required");
  return session;
}

export async function createDevice(request: Request, env: Env, now: Date): Promise<Response> {
  const session = await requireAdmin(request, env, now);
  const body = await readJson(request);
  const name = typeof body.name === "string" ? body.name.trim() : "";
  const kind = body.kind;
  if (name.length < 1 || name.length > 60) throw new HttpError(400, "validation_failed", "name must be 1 to 60 characters");
  if (kind !== "display" && kind !== "shortcut") {
    throw new HttpError(400, "validation_failed", "kind must be display or shortcut");
  }
  const deviceId = crypto.randomUUID();
  const token = generateApiToken();
  const stamp = now.toISOString();
  await env.DB.prepare(
    "INSERT INTO devices (id, household_id, name, kind, created_at) VALUES (?, ?, ?, ?, ?)",
  )
    .bind(deviceId, session.householdId, name, kind, stamp)
    .run();
  await env.DB.prepare(
    "INSERT INTO api_tokens (token_hash, device_id, household_id, scope, created_at) VALUES (?, ?, ?, ?, ?)",
  )
    .bind(await sha256Hex(token), deviceId, session.householdId, KIND_SCOPE[kind], stamp)
    .run();
  // The token is returned once and never stored in plain text.
  return json({ device: { id: deviceId, name, kind }, token }, 201);
}

export async function rotateDevice(request: Request, env: Env, now: Date, rawId: string): Promise<Response> {
  const session = await requireAdmin(request, env, now);
  const deviceId = parseId(rawId);
  const device = await env.DB.prepare(
    "SELECT kind FROM devices WHERE id = ? AND household_id = ? AND revoked_at IS NULL",
  )
    .bind(deviceId, session.householdId)
    .first<{ kind: keyof typeof KIND_SCOPE }>();
  if (!device) throw new HttpError(404, "not_found", "Device not found");
  const stamp = now.toISOString();
  const token = generateApiToken();
  await env.DB.prepare(
    "UPDATE api_tokens SET revoked_at = ? WHERE device_id = ? AND household_id = ? AND revoked_at IS NULL",
  )
    .bind(stamp, deviceId, session.householdId)
    .run();
  await env.DB.prepare(
    "INSERT INTO api_tokens (token_hash, device_id, household_id, scope, created_at) VALUES (?, ?, ?, ?, ?)",
  )
    .bind(await sha256Hex(token), deviceId, session.householdId, KIND_SCOPE[device.kind], stamp)
    .run();
  return json({ device: { id: deviceId }, token });
}

export async function revokeDevice(request: Request, env: Env, now: Date, rawId: string): Promise<Response> {
  const session = await requireAdmin(request, env, now);
  const deviceId = parseId(rawId);
  const result = await env.DB.prepare(
    "UPDATE devices SET revoked_at = ? WHERE id = ? AND household_id = ? AND revoked_at IS NULL",
  )
    .bind(now.toISOString(), deviceId, session.householdId)
    .run();
  if (result.meta.changes === 0) throw new HttpError(404, "not_found", "Device not found");
  return json({ ok: true });
}

// ---- Admin: household location (sunrise, sunset, weather) --------------------

export async function getLocation(request: Request, env: Env, now: Date): Promise<Response> {
  // Read-only: no CSRF token is needed for a GET, but the caller must still be an admin.
  const session = await requireSession(request, env, now);
  if (session.role !== "admin") throw new HttpError(403, "forbidden", "Admin access required");
  const row = await env.DB.prepare("SELECT latitude, longitude FROM households WHERE id = ?")
    .bind(session.householdId)
    .first<{ latitude: number | null; longitude: number | null }>();
  return json({ latitude: row?.latitude ?? null, longitude: row?.longitude ?? null });
}

export async function setLocation(request: Request, env: Env, now: Date): Promise<Response> {
  const session = await requireAdmin(request, env, now);
  const body = await readJson(request);
  const latitude = body.latitude ?? null;
  const longitude = body.longitude ?? null;
  const bothEmpty = latitude === null && longitude === null;
  const valid = (value: unknown, limit: number) => typeof value === "number" && Number.isFinite(value) && Math.abs(value) <= limit;
  if (!bothEmpty && !(valid(latitude, 90) && valid(longitude, 180))) {
    throw new HttpError(400, "validation_failed", "latitude must be -90 to 90 and longitude -180 to 180, or both null");
  }
  await env.DB.prepare("UPDATE households SET latitude = ?, longitude = ? WHERE id = ?")
    .bind(latitude, longitude, session.householdId)
    .run();
  return json({ latitude, longitude });
}
