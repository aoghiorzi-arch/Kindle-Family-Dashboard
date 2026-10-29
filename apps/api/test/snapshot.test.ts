import { test } from "node:test";
import assert from "node:assert/strict";
import { handle } from "../src/worker.ts";
import { bearer, createDevice, makeEnv, openDatabase, request, seed, signIn, validateSnapshotSchema } from "./helpers.ts";

async function setup(timezone = "Europe/London") {
  const db = openDatabase();
  seed(db, timezone);
  const env = makeEnv(db);
  const alex = await signIn(env, "a1");
  const display = await createDevice(env, alex, "display", "Hall display");
  return { db, env, alex, display };
}

const add = async (env: ReturnType<typeof makeEnv>, s: { cookie: string; csrf: string }, title: string) =>
  handle(request("/api/shopping", { method: "POST", body: { title }, cookie: s.cookie, csrf: s.csrf }), env);

test("the display gets a contract-valid, read-only snapshot", async () => {
  const { env, alex, display } = await setup();
  await add(env, alex, "Milk");
  const res = await handle(request("/api/device/snapshot", { headers: bearer(display.token) }), env, new Date("2026-10-29T08:00:00Z"));
  assert.equal(res.status, 200);
  const snapshot = await res.json();
  assert.equal(validateSnapshotSchema(snapshot), true, JSON.stringify(validateSnapshotSchema.errors));
  assert.equal(res.headers.get("ETag")?.startsWith('"'), true);
});

test("done items are left out of the snapshot", async () => {
  const { env, alex, display, db } = await setup();
  await add(env, alex, "Milk");
  await add(env, alex, "Bread");
  const bread = db.prepare("SELECT id, version FROM shopping_items WHERE title = 'Bread'").get() as { id: string; version: number };
  await handle(request(`/api/shopping/${bread.id}`, { method: "PATCH", body: { version: bread.version, done: true }, cookie: alex.cookie, csrf: alex.csrf }), env);
  const snapshot = (await (await handle(request("/api/device/snapshot", { headers: bearer(display.token) }), env)).json()) as {
    shopping: { remainingCount: number; items: { title: string }[] };
  };
  assert.equal(snapshot.shopping.remainingCount, 1);
  assert.deepEqual(snapshot.shopping.items.map((i) => i.title), ["Milk"]);
});

test("the revision changes when the list changes and stays put when it does not", async () => {
  const { env, alex, display } = await setup();
  const get = async () => (await handle(request("/api/device/snapshot", { headers: bearer(display.token) }), env)).headers.get("ETag");
  const before = await get();
  assert.equal(await get(), before, "unchanged content keeps its revision");
  await add(env, alex, "Eggs");
  assert.notEqual(await get(), before);
});

test("a matching If-None-Match returns 304 with no body", async () => {
  const { env, display } = await setup();
  const first = await handle(request("/api/device/snapshot", { headers: bearer(display.token) }), env);
  const etag = first.headers.get("ETag") ?? "";
  const second = await handle(request("/api/device/snapshot", { headers: { ...bearer(display.token), "If-None-Match": etag } }), env);
  assert.equal(second.status, 304);
  assert.equal(await second.text(), "");
});

test("more than seven unchecked items keep the list bounded and report the overflow", async () => {
  const { env, alex, display } = await setup();
  for (let n = 1; n <= 9; n += 1) await add(env, alex, `Item ${n}`);
  const snapshot = (await (await handle(request("/api/device/snapshot", { headers: bearer(display.token) }), env)).json()) as {
    shopping: { remainingCount: number; items: unknown[]; overflow: number };
  };
  assert.equal(validateSnapshotSchema(snapshot), true, JSON.stringify(validateSnapshotSchema.errors));
  assert.equal(snapshot.shopping.items.length, 7);
  assert.equal(snapshot.shopping.remainingCount, 9);
  assert.equal(snapshot.shopping.overflow, 2);
});

test("the snapshot date follows the household timezone", async () => {
  const { env, display } = await setup("Asia/Tokyo");
  const snapshot = (await (await handle(request("/api/device/snapshot", { headers: bearer(display.token) }), env, new Date("2026-10-29T23:30:00Z"))).json()) as {
    localDate: string;
    timezone: string;
  };
  assert.equal(snapshot.timezone, "Asia/Tokyo");
  assert.equal(snapshot.localDate, "2026-10-30");
});

test("the snapshot holds only the shopping list: no tokens, households or member names", async () => {
  const { env, alex, display } = await setup();
  await add(env, alex, "Milk");
  const text = await (await handle(request("/api/device/snapshot", { headers: bearer(display.token) }), env)).text();
  // Exact-match checks: short ids such as "a1" also occur inside the hex revision hash.
  for (const forbidden of ["kfd_", "Household One", "Alex", "Sam", "household_id", "member", "token", "csrf", "Set-Cookie"]) {
    assert.equal(text.includes(forbidden), false, `snapshot leaked ${forbidden}`);
  }
  const keys = Object.keys(JSON.parse(text)).sort();
  assert.deepEqual(keys, ["calendar", "clock", "expiresAt", "generatedAt", "localDate", "modules", "news", "reflection", "revision", "schemaVersion", "shopping", "sun", "timezone", "weather"]);
});

test("another household's list does not appear in this display's snapshot", async () => {
  const { env, display } = await setup();
  const other = await signIn(env, "x1");
  await add(env, other, "Other household secret item");
  const text = await (await handle(request("/api/device/snapshot", { headers: bearer(display.token) }), env)).text();
  assert.equal(text.includes("Other household secret item"), false);
});
