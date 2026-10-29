// Who is calling. Household identity always comes from the stored credential, never from the request body.
import { HttpError } from "./http.ts";
import type { Env } from "./env.ts";
import { isApiTokenShape, randomSecret, sha256Hex } from "../../../packages/core/src/index.ts";

export const SESSION_COOKIE = "kfd_session";
export const SESSION_DAYS = 14;
export const CSRF_HEADER = "X-CSRF-Token";

export interface MemberSession {
  memberId: string;
  householdId: string;
  role: "admin" | "member";
  csrfToken: string;
}

export interface DeviceCredential {
  deviceId: string;
  householdId: string;
  scope: "snapshot:read" | "shopping:add";
}

function cookieValue(request: Request, name: string): string | null {
  const header = request.headers.get("Cookie") ?? "";
  for (const part of header.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return rest.join("=");
  }
  return null;
}

export async function requireSession(request: Request, env: Env, now: Date): Promise<MemberSession> {
  const raw = cookieValue(request, SESSION_COOKIE);
  if (!raw) throw new HttpError(401, "unauthenticated", "Sign in required");
  const row = await env.DB.prepare(
    `SELECT s.csrf_token, s.expires_at, m.id AS member_id, m.household_id, m.role
       FROM sessions s JOIN members m ON m.id = s.member_id
      WHERE s.token_hash = ?`,
  )
    .bind(await sha256Hex(raw))
    .first<{ csrf_token: string; expires_at: string; member_id: string; household_id: string; role: "admin" | "member" }>();
  if (!row || row.expires_at <= now.toISOString()) throw new HttpError(401, "unauthenticated", "Sign in required");
  return {
    memberId: row.member_id,
    householdId: row.household_id,
    role: row.role,
    csrfToken: row.csrf_token,
  };
}

// Writes from the browser must come from the family app's origin and carry the session's CSRF token.
export function requireCsrf(request: Request, env: Env, session: MemberSession): void {
  if (request.headers.get("Origin") !== env.PUBLIC_ORIGIN) {
    throw new HttpError(403, "bad_origin", "Request origin is not allowed");
  }
  if (request.headers.get(CSRF_HEADER) !== session.csrfToken) {
    throw new HttpError(403, "bad_csrf", "CSRF check failed");
  }
}

export async function requireDevice(
  request: Request,
  env: Env,
  allowedScopes: DeviceCredential["scope"][],
): Promise<DeviceCredential> {
  const header = request.headers.get("Authorization") ?? "";
  const token = header.startsWith("Bearer ") ? header.slice(7) : "";
  if (!isApiTokenShape(token)) throw new HttpError(401, "unauthenticated", "Valid credential required");
  const row = await env.DB.prepare(
    `SELECT t.device_id, t.household_id, t.scope
       FROM api_tokens t JOIN devices d ON d.id = t.device_id
      WHERE t.token_hash = ? AND t.revoked_at IS NULL AND d.revoked_at IS NULL`,
  )
    .bind(await sha256Hex(token))
    .first<{ device_id: string; household_id: string; scope: DeviceCredential["scope"] }>();
  if (!row) throw new HttpError(401, "unauthenticated", "Valid credential required");
  if (!allowedScopes.includes(row.scope)) throw new HttpError(403, "forbidden", "Credential cannot use this endpoint");
  return { deviceId: row.device_id, householdId: row.household_id, scope: row.scope };
}

export async function createSession(env: Env, memberId: string, now: Date): Promise<string> {
  const token = randomSecret(32);
  const expires = new Date(now.getTime() + SESSION_DAYS * 24 * 60 * 60 * 1000);
  await env.DB.prepare(
    "INSERT INTO sessions (token_hash, member_id, csrf_token, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
  )
    .bind(await sha256Hex(token), memberId, randomSecret(32), expires.toISOString(), now.toISOString())
    .run();
  return token;
}

export function sessionCookie(token: string): string {
  return `${SESSION_COOKIE}=${token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${SESSION_DAYS * 86400}`;
}

export function clearSessionCookie(): string {
  return `${SESSION_COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0`;
}
