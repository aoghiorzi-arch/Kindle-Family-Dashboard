import { test } from "node:test";
import assert from "node:assert/strict";
import { handle } from "../src/worker.ts";
import { bearer, createDevice, makeEnv, openDatabase, request, seed, signIn } from "./helpers.ts";

async function setup() {
  const db = openDatabase();
  seed(db);
  const env = makeEnv(db);
  const alex = await signIn(env, "a1");
  const sam = await signIn(env, "m1");
  return { db, env, alex, sam };
}

const write = (path: string, s: { cookie: string; csrf: string }, method: string, body?: unknown) =>
  request(path, { method, body, cookie: s.cookie, csrf: s.csrf });

async function create(env: ReturnType<typeof makeEnv>, s: { cookie: string; csrf: string }, title: string) {
  const res = await handle(write("/api/shopping", s, "POST", { title }), env);
  assert.equal(res.status, 201);
  return ((await res.json()) as { item: { id: string; version: number; position: number } }).item;
}

test("two family members see the same list", async () => {
  const { env, alex, sam } = await setup();
  await create(env, alex, "Milk");
  const res = await handle(request("/api/shopping", { cookie: sam.cookie }), env);
  const items = ((await res.json()) as { items: { title: string }[] }).items;
  assert.deepEqual(items.map((i) => i.title), ["Milk"]);
});

test("items keep insertion order via position and reorder is persisted", async () => {
  const { env, alex } = await setup();
  const milk = await create(env, alex, "Milk");
  const bread = await create(env, alex, "Bread");
  assert.ok(bread.position > milk.position);
  // position is a sort key; the client sets the positions of the items it moves. Ties keep creation order.
  const res = await handle(write(`/api/shopping/${bread.id}`, alex, "PATCH", { version: bread.version, position: 0 }), env);
  assert.equal(res.status, 200);
  const moved = await handle(write(`/api/shopping/${milk.id}`, alex, "PATCH", { version: milk.version, position: 1 }), env);
  assert.equal(moved.status, 200);
  const list = ((await (await handle(request("/api/shopping", { cookie: alex.cookie }), env)).json()) as { items: { title: string }[] }).items;
  assert.deepEqual(list.map((i) => i.title), ["Bread", "Milk"]);
});

test("completing an item and deleting it both need the current version", async () => {
  const { env, alex } = await setup();
  const milk = await create(env, alex, "Milk");
  const done = await handle(write(`/api/shopping/${milk.id}`, alex, "PATCH", { version: milk.version, done: true }), env);
  assert.equal(done.status, 200);
  const item = ((await done.json()) as { item: { done: boolean; version: number } }).item;
  assert.equal(item.done, true);
  assert.equal(item.version, milk.version + 1);

  const stale = await handle(write(`/api/shopping/${milk.id}?version=${milk.version}`, alex, "DELETE"), env);
  assert.equal(stale.status, 409);
  const ok = await handle(write(`/api/shopping/${milk.id}?version=${item.version}`, alex, "DELETE"), env);
  assert.equal(ok.status, 200);
});

test("a stale PATCH is refused with the current item, so no edit is silently lost", async () => {
  const { env, alex, sam } = await setup();
  const milk = await create(env, alex, "Milk");
  await handle(write(`/api/shopping/${milk.id}`, alex, "PATCH", { version: milk.version, title: "Oat milk" }), env);
  const res = await handle(write(`/api/shopping/${milk.id}`, sam, "PATCH", { version: milk.version, done: true }), env);
  assert.equal(res.status, 409);
  const body = (await res.json()) as { error: { code: string; current: { title: string; done: boolean } } };
  assert.equal(body.error.code, "conflict");
  assert.equal(body.error.current.title, "Oat milk");
  assert.equal(body.error.current.done, false);
});

test("concurrent writes from the same version: exactly one succeeds", async () => {
  const { env, alex, sam } = await setup();
  const milk = await create(env, alex, "Milk");
  const results = await Promise.all([
    handle(write(`/api/shopping/${milk.id}`, alex, "PATCH", { version: milk.version, done: true }), env),
    handle(write(`/api/shopping/${milk.id}`, sam, "PATCH", { version: milk.version, title: "Semi-skimmed" }), env),
  ]);
  assert.deepEqual(results.map((r) => r.status).sort(), [200, 409]);
});

test("one household cannot read or change another household's item", async () => {
  const { db, env, alex } = await setup();
  const milk = await create(env, alex, "Milk");
  const other = await signIn(env, "x1");
  const patch = await handle(write(`/api/shopping/${milk.id}`, other, "PATCH", { version: milk.version, done: true }), env);
  assert.equal(patch.status, 404);
  const del = await handle(write(`/api/shopping/${milk.id}?version=${milk.version}`, other, "DELETE"), env);
  assert.equal(del.status, 404);
  const list = ((await (await handle(request("/api/shopping", { cookie: other.cookie }), env)).json()) as { items: unknown[] }).items;
  assert.equal(list.length, 0);
  assert.equal((db.prepare("SELECT done FROM shopping_items WHERE id = ?").get(milk.id) as { done: number }).done, 0);
});

test("the body cannot choose the household", async () => {
  const { db, env, alex } = await setup();
  const res = await handle(write("/api/shopping", alex, "POST", { title: "Eggs", household_id: "h2" }), env);
  assert.equal(res.status, 201);
  const row = db.prepare("SELECT household_id FROM shopping_items WHERE title = 'Eggs'").get() as { household_id: string };
  assert.equal(row.household_id, "h1");
});

test("titles are checked: empty, too long, and control characters are refused", async () => {
  const { env, alex } = await setup();
  for (const title of ["", "   ", "x".repeat(61), "bad\u0007bell", 42]) {
    const res = await handle(write("/api/shopping", alex, "POST", { title }), env);
    assert.equal(res.status, 400, JSON.stringify(title));
  }
});

test("a 60-character title is accepted and counted in code points", async () => {
  const { env, alex } = await setup();
  const res = await handle(write("/api/shopping", alex, "POST", { title: "é".repeat(60) }), env);
  assert.equal(res.status, 201);
});

test("bodies must be JSON objects under the size limit", async () => {
  const { env, alex } = await setup();
  const cookieCsrf = { cookie: alex.cookie, csrf: alex.csrf };
  const notJson = await handle(request("/api/shopping", { method: "POST", rawBody: "{", headers: { "Content-Type": "application/json" }, ...cookieCsrf }), env);
  assert.equal(notJson.status, 400);
  const wrongType = await handle(request("/api/shopping", { method: "POST", rawBody: "{}", headers: { "Content-Type": "text/plain" }, ...cookieCsrf }), env);
  assert.equal(wrongType.status, 415);
  const big = await handle(request("/api/shopping", { method: "POST", rawBody: JSON.stringify({ title: "x".repeat(5000) }), headers: { "Content-Type": "application/json" }, ...cookieCsrf }), env);
  assert.equal(big.status, 413);
  const array = await handle(request("/api/shopping", { method: "POST", rawBody: "[]", headers: { "Content-Type": "application/json" }, ...cookieCsrf }), env);
  assert.equal(array.status, 400);
});

test("a Shortcut token adds an item for its own household", async () => {
  const { env, alex } = await setup();
  const shortcut = await createDevice(env, alex, "shortcut", "Phone shortcut");
  const res = await handle(request("/api/shopping", { method: "POST", body: { title: "Bananas" }, headers: bearer(shortcut.token) }), env);
  assert.equal(res.status, 201);
  const list = ((await (await handle(request("/api/shopping", { cookie: alex.cookie }), env)).json()) as { items: { title: string }[] }).items;
  assert.ok(list.some((i) => i.title === "Bananas"));
});

test("an empty patch is refused", async () => {
  const { env, alex } = await setup();
  const milk = await create(env, alex, "Milk");
  const res = await handle(write(`/api/shopping/${milk.id}`, alex, "PATCH", { version: milk.version }), env);
  assert.equal(res.status, 400);
});

test("unknown routes and wrong methods get clean errors", async () => {
  const { env } = await setup();
  assert.equal((await handle(request("/api/nope"), env)).status, 404);
  assert.equal((await handle(request("/api/shopping", { method: "PUT" }), env)).status, 405);
});

test("responses carry no-store and a restrictive CSP", async () => {
  const { env } = await setup();
  const res = await handle(request("/api/health"), env);
  assert.equal(res.headers.get("Cache-Control"), "no-store");
  assert.ok(res.headers.get("Content-Security-Policy")?.includes("default-src 'none'"));
});
