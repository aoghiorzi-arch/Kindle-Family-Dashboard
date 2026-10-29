// Who is calling. Household identity always comes from the stored credential, never from the request body.
import { HttpError } from "./http.ts";
import type { Env } from "./env.ts";
import { isApiTokenShape, randomSecret, sha256Hex, toBase64Url } from "../../../packages/core/src/index.ts";
import { ACCESS_HEADER, verifyAccessJwt } from "./access.ts";

export const SESSION_COOKIE = "kfd_session";
export const SESSION_DAYS = 14;
export const CSRF_HEADER = "X-CSRF-Token";

export interface MemberSession {
  memberId: string;
  displayName: string;
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
    `SELECT s.csrf_token, s.expires_at, m.id AS member_id, m.display_name, m.household_id, m.role
       FROM sessions s JOIN members m ON m.id = s.member_id
      WHERE s.token_hash = ?`,
  )
    .bind(await sha256Hex(raw))
    .first<{
      csrf_token: string;
      expires_at: string;
      member_id: string;
      display_name: string;
      household_id: string;
      role: "admin" | "member";
    }>();
  if (!row || row.expires_at <= now.toISOString()) throw new HttpError(401, "unauthenticated", "Sign in required");
  return {
    memberId: row.member_id,
    displayName: row.display_name,
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

// ---- Identity: Cloudflare Access in production, development cookie locally ---------

export function accessConfigured(env: Env): boolean {
  return Boolean(env.ACCESS_TEAM_DOMAIN && env.ACCESS_AUD);
}

// Access mode: the CSRF token is derived from the server secret, the member and the Access session, so it changes when the session does.
async function accessCsrf(env: Env, memberId: string, sub: string, iat: number): Promise<string> {
  if (!env.CSRF_SECRET) throw new HttpError(500, "internal", "Server is not configured");
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(env.CSRF_SECRET), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(`${memberId}|${sub}|${iat}`));
  return toBase64Url(new Uint8Array(mac));
}

// Who is calling, for every browser route. Access identifies the person; the household comes from the matched member row.
export async function requireMember(request: Request, env: Env, now: Date): Promise<MemberSession> {
  if (!accessConfigured(env)) return requireSession(request, env, now);
  const token = request.headers.get(ACCESS_HEADER);
  if (!token) throw new HttpError(401, "unauthenticated", "Sign in required");
  const identity = await verifyAccessJwt(token, { teamDomain: env.ACCESS_TEAM_DOMAIN!, aud: env.ACCESS_AUD! }, now);
  const row = await env.DB.prepare(
    "SELECT id, display_name, household_id, role FROM members WHERE lower(email) = ?",
  )
    .bind(identity.email)
    .first<{ id: string; display_name: string; household_id: string; role: "admin" | "member" }>();
  if (!row) throw new HttpError(403, "not_a_member", "This email address is not a member of a household");
  return {
    memberId: row.id,
    displayName: row.display_name,
    householdId: row.household_id,
    role: row.role,
    csrfToken: await accessCsrf(env, row.id, identity.sub, identity.iat),
  };
}
