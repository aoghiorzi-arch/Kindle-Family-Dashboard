// Cloudflare Access: real RSA keys and signed tokens, with the team's certificate endpoint stubbed.
import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { handle } from "../src/worker.ts";
import { clearAccessKeyCache, verifyAccessJwt, ACCESS_HEADER } from "../src/access.ts";
import { bearer, createDevice, makeEnv, openDatabase, request, seed } from "./helpers.ts";
import type { Env } from "../src/env.ts";

const TEAM = "family.cloudflareaccess.test";
const AUD = "aud-family-hub";
const ORIGIN = "https://family.test";
const originalFetch = globalThis.fetch;

const b64url = (bytes: Uint8Array) => {
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
};
const b64urlJson = (value: unknown) => b64url(new TextEncoder().encode(JSON.stringify(value)));

async function newKey() {
  return crypto.subtle.generateKey(
    { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
    true,
    ["sign", "verify"],
  );
}

async function jwksFor(kid: string, publicKey: CryptoKey) {
  const jwk = await crypto.subtle.exportKey("jwk", publicKey);
  return { keys: [{ ...jwk, kid, alg: "RS256", use: "sig" }] };
}

async function signToken(privateKey: CryptoKey, kid: string, claims: Record<string, unknown>, header: Record<string, unknown> = {}) {
  const now = Math.floor(Date.now() / 1000);
  const payload = { aud: [AUD], iss: `https://${TEAM}`, iat: now, exp: now + 600, email: "alex@family.test", sub: "user-1", ...claims };
  const signingInput = `${b64urlJson({ alg: "RS256", kid, typ: "JWT", ...header })}.${b64urlJson(payload)}`;
  const signature = new Uint8Array(await crypto.subtle.sign("RSASSA-PKCS1-v1_5", privateKey, new TextEncoder().encode(signingInput)));
  return `${signingInput}.${b64url(signature)}`;
}

// Serves the team's certificate endpoint from memory and passes every other URL to the real fetch.
function serveCerts(jwks: unknown) {
  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (url === `https://${TEAM}/cdn-cgi/access/certs`) {
      return new Response(JSON.stringify(jwks), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return originalFetch(input, init);
  }) as typeof fetch;
}

beforeEach(() => clearAccessKeyCache());
afterEach(() => {
  globalThis.fetch = originalFetch;
  clearAccessKeyCache();
});

async function accessEnv() {
  const db = openDatabase();
  seed(db);
  db.prepare("UPDATE members SET email = 'alex@family.test' WHERE id = 'a1'").run();
  db.prepare("UPDATE members SET email = 'sam@family.test' WHERE id = 'm1'").run();
  const env: Env = { ...makeEnv(db, "production"), ACCESS_TEAM_DOMAIN: TEAM, ACCESS_AUD: AUD, CSRF_SECRET: "test-csrf-secret" };
  return { db, env };
}

const withAccess = (token: string, extra: Record<string, string> = {}) => ({ [ACCESS_HEADER]: token, ...extra });

// ---- Token verification --------------------------------------------------------

test("a correctly signed token for the right audience and issuer is accepted", async () => {
  const key = await newKey();
  serveCerts(await jwksFor("k1", key.publicKey));
  const token = await signToken(key.privateKey, "k1", { email: "Alex@Family.Test" });
  const identity = await verifyAccessJwt(token, { teamDomain: TEAM, aud: AUD }, new Date());
  assert.deepEqual(identity, { email: "alex@family.test", sub: "user-1", iat: identity.iat });
});

test("tokens are refused for the wrong audience, issuer, expiry, algorithm, key id or a tampered payload", async () => {
  const key = await newKey();
  const other = await newKey();
  serveCerts(await jwksFor("k1", key.publicKey));
  const cases: Array<[string, Promise<string>]> = [
    ["wrong audience", signToken(key.privateKey, "k1", { aud: ["someone-else"] })],
    ["wrong issuer", signToken(key.privateKey, "k1", { iss: "https://attacker.example" })],
    ["expired", signToken(key.privateKey, "k1", { exp: Math.floor(Date.now() / 1000) - 3600 })],
    ["unknown key id", signToken(key.privateKey, "k-unknown", {})],
    ["signed by another key", signToken(other.privateKey, "k1", {})],
    ["algorithm not RS256", signToken(key.privateKey, "k1", {}, { alg: "HS256" })],
  ];
  for (const [label, pending] of cases) {
    const token = await pending;
    await assert.rejects(verifyAccessJwt(token, { teamDomain: TEAM, aud: AUD }, new Date()), { status: 401 }, label);
  }
  const good = await signToken(key.privateKey, "k1", {});
  const [h, p, s] = good.split(".");
  const tampered = `${h}.${b64urlJson({ ...JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(p.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0)))), email: "sam@family.test" })}.${s}`;
  await assert.rejects(verifyAccessJwt(tampered, { teamDomain: TEAM, aud: AUD }, new Date()), { status: 401 }, "tampered payload");
});

test("malformed tokens are refused", async () => {
  serveCerts({ keys: [] });
  for (const token of ["", "a.b", "a.b.c", "not-a-jwt"]) {
    await assert.rejects(verifyAccessJwt(token, { teamDomain: TEAM, aud: AUD }, new Date()), { status: 401 }, token);
  }
});

// ---- Browser routes in Access mode ------------------------------------------

test("a family member with a valid assertion signs in; the CSRF token is needed for writes", async () => {
  const key = await newKey();
  serveCerts(await jwksFor("k1", key.publicKey));
  const { env } = await accessEnv();
  const token = await signToken(key.privateKey, "k1", { email: "alex@family.test" });
  const me = await handle(request("/api/me", { headers: withAccess(token) }), env);
  assert.equal(me.status, 200);
  const body = (await me.json()) as { memberId: string; csrfToken: string; role: string };
  assert.equal(body.memberId, "a1");
  assert.equal(body.role, "admin");
  const created = await handle(request("/api/shopping", {
    method: "POST", body: { title: "Milk" }, headers: withAccess(token), csrf: body.csrfToken, origin: ORIGIN,
  }), env);
  assert.equal(created.status, 201);
  const noCsrf = await handle(request("/api/shopping", { method: "POST", body: { title: "Eggs" }, headers: withAccess(token), origin: ORIGIN }), env);
  assert.equal(noCsrf.status, 403);
});

test("a valid assertion for an email that is not a member is refused", async () => {
  const key = await newKey();
  serveCerts(await jwksFor("k1", key.publicKey));
  const { env } = await accessEnv();
  const token = await signToken(key.privateKey, "k1", { email: "stranger@elsewhere.test" });
  const res = await handle(request("/api/me", { headers: withAccess(token) }), env);
  assert.equal(res.status, 403);
  assert.equal(((await res.json()) as { error: { code: string } }).error.code, "not_a_member");
});

test("no assertion means no access in Access mode, and the development login stays off", async () => {
  const { env } = await accessEnv();
  assert.equal((await handle(request("/api/me"), env)).status, 401);
  assert.equal((await handle(request("/api/dev/login", { method: "POST", body: { memberId: "a1" } }), env)).status, 404);
  const health = (await (await handle(request("/api/health"), env)).json()) as { signIn: string };
  assert.equal(health.signIn, "cloudflare-access");
});

test("a Shortcut token still adds items with no Access assertion, on the Shortcut path", async () => {
  const key = await newKey();
  serveCerts(await jwksFor("k1", key.publicKey));
  const { env } = await accessEnv();
  const token = await signToken(key.privateKey, "k1", { email: "alex@family.test" });
  const me = (await (await handle(request("/api/me", { headers: withAccess(token) }), env)).json()) as { csrfToken: string };
  const created = await handle(request("/api/admin/devices", { method: "POST", body: { name: "Phone", kind: "shortcut" }, headers: withAccess(token), csrf: me.csrfToken, origin: ORIGIN }), env);
  const { token: shortcutToken } = (await created.json()) as { token: string };
  const add = await handle(request("/api/shortcut/shopping", { method: "POST", body: { title: "Bananas" }, headers: bearer(shortcutToken) }), env);
  assert.equal(add.status, 201);
});

test("an admin invites a member by email; duplicates and non-admin invites are refused", async () => {
  const key = await newKey();
  serveCerts(await jwksFor("k1", key.publicKey));
  const { env } = await accessEnv();
  const alexToken = await signToken(key.privateKey, "k1", { email: "alex@family.test" });
  const samToken = await signToken(key.privateKey, "k1", { email: "sam@family.test" });
  const alexCsrf = ((await (await handle(request("/api/me", { headers: withAccess(alexToken) }), env)).json()) as { csrfToken: string }).csrfToken;
  const samCsrf = ((await (await handle(request("/api/me", { headers: withAccess(samToken) }), env)).json()) as { csrfToken: string }).csrfToken;
  const invite = (token: string, csrf: string, email: string) =>
    handle(request("/api/admin/members", { method: "POST", body: { displayName: "Jo", email, role: "member" }, headers: withAccess(token), csrf, origin: ORIGIN }), env);

  assert.equal((await invite(samToken, samCsrf, "jo@family.test")).status, 403, "members cannot invite");
  assert.equal((await invite(alexToken, alexCsrf, "not-an-email")).status, 400);
  const ok = await invite(alexToken, alexCsrf, "Jo@Family.Test");
  assert.equal(ok.status, 201);
  assert.equal((await invite(alexToken, alexCsrf, "jo@family.test")).status, 409);

  const joToken = await signToken(key.privateKey, "k1", { email: "jo@family.test", sub: "user-jo" });
  const jo = await handle(request("/api/me", { headers: withAccess(joToken) }), env);
  assert.equal(jo.status, 200, "the invited member can now sign in");
  const listed = (await (await handle(request("/api/admin/members", { headers: withAccess(alexToken) }), env)).json()) as { members: { email: string }[] };
  assert.ok(listed.members.some((m) => m.email === "jo@family.test"));
});

test("Access mode fails closed when the signing secret is missing", async () => {
  const key = await newKey();
  serveCerts(await jwksFor("k1", key.publicKey));
  const { env } = await accessEnv();
  env.CSRF_SECRET = undefined;
  const token = await signToken(key.privateKey, "k1", { email: "alex@family.test" });
  assert.equal((await handle(request("/api/me", { headers: withAccess(token) }), env)).status, 500);
});
