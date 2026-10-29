// Endpoints the phone editor depends on.
import { test } from "node:test";
import assert from "node:assert/strict";
import { handle } from "../src/worker.ts";
import { bearer, createDevice, makeEnv, openDatabase, request, seed, signIn, validateSnapshotSchema } from "./helpers.ts";

function setup() {
  const db = openDatabase();
  seed(db);
  return { env: makeEnv(db) };
}

test("/api/me returns the member's name for the editor header", async () => {
  const { env } = setup();
  const alex = await signIn(env, "a1");
  const body = (await (await handle(request("/api/me", { cookie: alex.cookie }), env)).json()) as { displayName: string };
  assert.equal(body.displayName, "Alex");
});

test("the phone preview is the snapshot the display receives, and is contract-valid", async () => {
  const { env } = setup();
  const alex = await signIn(env, "a1");
  await handle(request("/api/shopping", { method: "POST", body: { title: "Milk" }, cookie: alex.cookie, csrf: alex.csrf }), env);
  const display = await createDevice(env, alex, "display");
  const now = new Date("2026-10-29T08:00:00Z");
  const preview = (await (await handle(request("/api/snapshot/preview", { cookie: alex.cookie }), env, now)).json()) as Record<string, unknown>;
  const device = (await (await handle(request("/api/device/snapshot", { headers: bearer(display.token) }), env, now)).json()) as Record<string, unknown>;
  assert.equal(validateSnapshotSchema(preview), true, JSON.stringify(validateSnapshotSchema.errors));
  assert.deepEqual(preview, device);
});

test("the preview requires a session", async () => {
  const { env } = setup();
  assert.equal((await handle(request("/api/snapshot/preview"), env)).status, 401);
});

test("the device list shows names and status, never token values", async () => {
  const { env } = setup();
  const alex = await signIn(env, "a1");
  const display = await createDevice(env, alex, "display", "Hall display");
  await handle(request(`/api/admin/devices/${display.id}`, { method: "DELETE", cookie: alex.cookie, csrf: alex.csrf }), env);
  const text = await (await handle(request("/api/admin/devices", { cookie: alex.cookie }), env)).text();
  assert.ok(text.includes("Hall display"));
  assert.ok(text.includes('"active":false'));
  assert.equal(text.includes(display.token), false);
  assert.equal(text.includes("kfd_"), false);
});

test("members cannot list devices and other households' devices are not shown", async () => {
  const { env } = setup();
  const sam = await signIn(env, "m1");
  assert.equal((await handle(request("/api/admin/devices", { cookie: sam.cookie }), env)).status, 403);
  const alex = await signIn(env, "a1");
  await createDevice(env, alex, "display", "Alex's display");
  const other = await signIn(env, "x1");
  const text = await (await handle(request("/api/admin/devices", { cookie: other.cookie }), env)).text();
  assert.equal(text.includes("Alex's display"), false);
});
