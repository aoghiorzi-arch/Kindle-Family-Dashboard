import { test } from "node:test";
import assert from "node:assert/strict";
import { handle } from "../src/worker.ts";
import { bearer, createDevice, makeEnv, openDatabase, request, seed, signIn } from "./helpers.ts";

function setup(environment = "local") {
  const db = openDatabase();
  seed(db);
  return { db, env: makeEnv(db, environment) };
}

test("health is public and reveals no household data", async () => {
  const { env } = setup();
  const res = await handle(request("/api/health"), env);
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { ok: true });
});

test("shopping requires a session", async () => {
  const { env } = setup();
  const res = await handle(request("/api/shopping"), env);
  assert.equal(res.status, 401);
  assert.equal((await res.json() as { error: { code: string } }).error.code, "unauthenticated");
});

test("dev sign-in is refused outside the local environment", async () => {
  const { env } = setup("production");
  const res = await handle(request("/api/dev/login", { method: "POST", body: { memberId: "a1" } }), env);
  assert.equal(res.status, 404);
  assert.equal(res.headers.get("Set-Cookie"), null);
});

test("session cookie is HttpOnly, Secure and SameSite=Strict", async () => {
  const { env } = setup();
  const res = await handle(request("/api/dev/login", { method: "POST", body: { memberId: "m1" } }), env);
  const cookie = res.headers.get("Set-Cookie") ?? "";
  for (const attr of ["HttpOnly", "Secure", "SameSite=Strict", "Path=/"]) assert.ok(cookie.includes(attr), attr);
});

test("browser writes need the CSRF token and the exact origin", async () => {
  const { env } = setup();
  const session = await signIn(env, "m1");
  const noCsrf = await handle(
    request("/api/shopping", { method: "POST", body: { title: "Milk" }, cookie: session.cookie, origin: "https://family.test" }),
    env,
  );
  assert.equal(noCsrf.status, 403);
  const wrongOrigin = await handle(
    request("/api/shopping", { method: "POST", body: { title: "Milk" }, cookie: session.cookie, csrf: session.csrf, origin: "https://evil.test" }),
    env,
  );
  assert.equal(wrongOrigin.status, 403);
  const noOrigin = await handle(
    request("/api/shopping", { method: "POST", body: { title: "Milk" }, cookie: session.cookie, csrf: session.csrf, origin: null }),
    env,
  );
  assert.equal(noOrigin.status, 403);
});

test("an expired session is rejected", async () => {
  const { env } = setup();
  const session = await signIn(env, "m1", new Date("2026-10-01T00:00:00Z"));
  const res = await handle(request("/api/me", { cookie: session.cookie }), env, new Date("2026-10-20T00:00:00Z"));
  assert.equal(res.status, 401);
});

test("logout invalidates the session", async () => {
  const { env } = setup();
  const session = await signIn(env, "m1");
  const out = await handle(request("/api/logout", { method: "POST", cookie: session.cookie, csrf: session.csrf }), env);
  assert.equal(out.status, 200);
  const after = await handle(request("/api/me", { cookie: session.cookie }), env);
  assert.equal(after.status, 401);
});

test("a display credential cannot read or write the shopping list", async () => {
  const { env } = setup();
  const admin = await signIn(env, "a1");
  const display = await createDevice(env, admin, "display");
  const read = await handle(request("/api/shopping", { headers: bearer(display.token) }), env);
  assert.equal(read.status, 401);
  const write = await handle(request("/api/shopping", { method: "POST", body: { title: "Eggs" }, headers: bearer(display.token) }), env);
  assert.equal(write.status, 403);
});

test("a shortcut credential can add but not read the list or fetch the snapshot", async () => {
  const { env } = setup();
  const admin = await signIn(env, "a1");
  const shortcut = await createDevice(env, admin, "shortcut", "Phone shortcut");
  const add = await handle(request("/api/shopping", { method: "POST", body: { title: "Eggs" }, headers: bearer(shortcut.token) }), env);
  assert.equal(add.status, 201);
  const snapshot = await handle(request("/api/device/snapshot", { headers: bearer(shortcut.token) }), env);
  assert.equal(snapshot.status, 403);
});

test("a revoked device stops working immediately", async () => {
  const { env } = setup();
  const admin = await signIn(env, "a1");
  const display = await createDevice(env, admin, "display");
  assert.equal((await handle(request("/api/device/snapshot", { headers: bearer(display.token) }), env)).status, 200);
  const revoke = await handle(
    request(`/api/admin/devices/${display.id}`, { method: "DELETE", cookie: admin.cookie, csrf: admin.csrf }),
    env,
  );
  assert.equal(revoke.status, 200);
  assert.equal((await handle(request("/api/device/snapshot", { headers: bearer(display.token) }), env)).status, 401);
});

test("rotating a device invalidates the old token and issues a new one", async () => {
  const { env } = setup();
  const admin = await signIn(env, "a1");
  const display = await createDevice(env, admin, "display");
  const rotated = await handle(
    request(`/api/admin/devices/${display.id}/rotate`, { method: "POST", cookie: admin.cookie, csrf: admin.csrf }),
    env,
  );
  assert.equal(rotated.status, 200);
  const { token } = (await rotated.json()) as { token: string };
  assert.notEqual(token, display.token);
  assert.equal((await handle(request("/api/device/snapshot", { headers: bearer(display.token) }), env)).status, 401);
  assert.equal((await handle(request("/api/device/snapshot", { headers: bearer(token) }), env)).status, 200);
});

test("only admins can create device credentials", async () => {
  const { env } = setup();
  const member = await signIn(env, "m1");
  const res = await handle(
    request("/api/admin/devices", { method: "POST", body: { name: "x", kind: "display" }, cookie: member.cookie, csrf: member.csrf }),
    env,
  );
  assert.equal(res.status, 403);
});

test("device tokens are stored only as hashes", async () => {
  const { db, env } = setup();
  const admin = await signIn(env, "a1");
  const display = await createDevice(env, admin, "display");
  const rows = db.prepare("SELECT token_hash FROM api_tokens").all() as { token_hash: string }[];
  assert.equal(rows.length, 1);
  assert.notEqual(rows[0].token_hash, display.token);
  assert.equal(rows.some((r) => r.token_hash.includes(display.token)), false);
});

test("a malformed or unknown bearer token gets 401 without detail", async () => {
  const { env } = setup();
  for (const token of ["", "Bearer", "kfd_short", "kfd_" + "A".repeat(43)]) {
    const res = await handle(request("/api/device/snapshot", { headers: { Authorization: token } }), env);
    assert.equal(res.status, 401, token);
    assert.equal((await res.text()).includes("kfd_"), false);
  }
});
