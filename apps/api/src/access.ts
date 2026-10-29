// Cloudflare Access: verifies the signed assertion Access attaches to each request that passed its login.
// The Worker checks the signature against the team's published keys, then the audience, issuer, expiry and algorithm.
import { HttpError } from "./http.ts";

export const ACCESS_HEADER = "Cf-Access-Jwt-Assertion";
const KEY_TTL_MS = 60 * 60 * 1000;
const CLOCK_SKEW_S = 60;

export interface AccessIdentity {
  email: string;
  sub: string;
  iat: number;
}

interface Jwk {
  kid: string;
  kty: string;
  n: string;
  e: string;
  alg?: string;
}

let keyCache: { teamDomain: string; fetchedAt: number; keys: Map<string, CryptoKey> } | null = null;

export function clearAccessKeyCache(): void {
  keyCache = null;
}

function b64urlBytes(value: string): Uint8Array<ArrayBuffer> {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function decodeJsonPart(part: string): Record<string, unknown> {
  try {
    return JSON.parse(new TextDecoder().decode(b64urlBytes(part))) as Record<string, unknown>;
  } catch {
    throw new HttpError(401, "unauthenticated", "Invalid access assertion");
  }
}

async function loadKeys(teamDomain: string, fetcher: typeof fetch, now: number): Promise<Map<string, CryptoKey>> {
  if (keyCache && keyCache.teamDomain === teamDomain && now - keyCache.fetchedAt < KEY_TTL_MS) return keyCache.keys;
  const response = await fetcher(`https://${teamDomain}/cdn-cgi/access/certs`, { redirect: "error" });
  if (!response.ok) throw new HttpError(503, "unavailable", "Sign-in keys are unavailable");
  const body = (await response.json()) as { keys?: Jwk[] };
  const keys = new Map<string, CryptoKey>();
  for (const jwk of body.keys ?? []) {
    if (jwk.kty !== "RSA" || !jwk.kid) continue;
    const key = await crypto.subtle.importKey(
      "jwk",
      { kty: "RSA", n: jwk.n, e: jwk.e, alg: "RS256", ext: true },
      { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
      false,
      ["verify"],
    );
    keys.set(jwk.kid, key);
  }
  keyCache = { teamDomain, fetchedAt: now, keys };
  return keys;
}

export async function verifyAccessJwt(
  token: string,
  config: { teamDomain: string; aud: string },
  now: Date,
  fetcher: typeof fetch = fetch,
): Promise<AccessIdentity> {
  const parts = token.split(".");
  if (parts.length !== 3) throw new HttpError(401, "unauthenticated", "Invalid access assertion");
  const [headerPart, payloadPart, signaturePart] = parts;
  const header = decodeJsonPart(headerPart);
  const payload = decodeJsonPart(payloadPart);

  if (header.alg !== "RS256" || typeof header.kid !== "string") {
    throw new HttpError(401, "unauthenticated", "Invalid access assertion");
  }
  const keys = await loadKeys(config.teamDomain, fetcher, now.getTime());
  const key = keys.get(header.kid);
  if (!key) throw new HttpError(401, "unauthenticated", "Invalid access assertion");

  const signed = new Uint8Array(new TextEncoder().encode(`${headerPart}.${payloadPart}`));
  const valid = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, b64urlBytes(signaturePart), signed);
  if (!valid) throw new HttpError(401, "unauthenticated", "Invalid access assertion");

  const seconds = Math.floor(now.getTime() / 1000);
  const audiences = Array.isArray(payload.aud) ? payload.aud : [payload.aud];
  if (!audiences.includes(config.aud)) throw new HttpError(401, "unauthenticated", "Invalid access assertion");
  if (payload.iss !== `https://${config.teamDomain}`) throw new HttpError(401, "unauthenticated", "Invalid access assertion");
  if (typeof payload.exp !== "number" || payload.exp <= seconds - CLOCK_SKEW_S) {
    throw new HttpError(401, "unauthenticated", "Access assertion expired");
  }
  if (typeof payload.iat !== "number" || payload.iat > seconds + CLOCK_SKEW_S) {
    throw new HttpError(401, "unauthenticated", "Invalid access assertion");
  }
  if (typeof payload.email !== "string" || typeof payload.sub !== "string") {
    throw new HttpError(401, "unauthenticated", "Invalid access assertion");
  }
  return { email: payload.email.toLowerCase(), sub: payload.sub, iat: payload.iat };
}
