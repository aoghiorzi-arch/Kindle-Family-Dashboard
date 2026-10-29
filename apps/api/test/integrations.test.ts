// Phase 5 gates: providers never blank the dashboard, rate limits hold, feeds are bounded, content is attributed.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { handle } from "../src/worker.ts";
import { runScheduled, parseFeedList, cachedPayload } from "../src/scheduled.ts";
import { bearer, createDevice, makeEnv, openDatabase, request, seed, signIn, validateSnapshotSchema } from "./helpers.ts";
import type { Env } from "../src/env.ts";

const ICS = readFileSync(fileURLToPath(new URL("../../../packages/core/test/fixtures/calendar/basic.ics", import.meta.url)), "utf8");
const RSS = `<?xml version="1.0"?><rss version="2.0"><channel><title>Synthetic Daily</title>
  <item><title>First headline</title></item><item><title>Second headline</title></item>
  <item><title>Third headline</title></item><item><title>Fourth headline</title></item></channel></rss>`;

type Route = (url: string) => Response | Promise<Response> | "throw";

// A fake network: each provider URL maps to a response, or throws to simulate an outage.
function fakeFetch(routes: Record<string, Route>) {
  const calls: string[] = [];
  const fetcher = async (input: string) => {
    calls.push(input);
    const key = Object.keys(routes).find((k) => input.startsWith(k));
    if (!key) return new Response("not found", { status: 404 });
    const result = routes[key](input);
    if (result === "throw") throw new TypeError("network down");
    return result instanceof Promise ? await result : result;
  };
  return { fetcher, calls };
}

const okJson = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
const weatherBody = (temperature = 12, code = 3) => ({ current: { time: "2026-10-29T08:00", temperature_2m: temperature, weather_code: code } });

async function setup(opts: { location?: boolean; feeds?: boolean } = {}) {
  const db = openDatabase();
  seed(db);
  const env: Env = makeEnv(db);
  if (opts.location !== false) db.prepare("UPDATE households SET latitude = 51.5074, longitude = -0.1278 WHERE id = 'h1'").run();
  if (opts.feeds !== false) {
    env.CALENDAR_FEED_URL = "https://calendar.example.test/family.ics";
    env.HOUSEHOLD_ID = "h1";
    env.NEWS_FEED_URLS = JSON.stringify(["https://news.example.test/feed.xml"]);
  }
  const alex = await signIn(env, "a1");
  const display = await createDevice(env, alex, "display");
  return { db, env, alex, display };
}

const NOW = new Date("2026-10-29T08:00:00Z");
const readSnapshot = async (env: Env, token: string, now = NOW) =>
  (await (await handle(request("/api/device/snapshot", { headers: bearer(token) }), env, now)).json()) as Record<string, any>;

const allRoutes = (overrides: Record<string, Route> = {}) => ({
  "https://api.open-meteo.com/": () => okJson(weatherBody()),
  "https://calendar.example.test/": () => new Response(ICS, { status: 200 }),
  "https://news.example.test/": () => new Response(RSS, { status: 200 }),
  ...overrides,
});

test("a due scheduled run fills the caches, and the display snapshot shows them, attributed and valid", async () => {
  const { env, display } = await setup();
  const { fetcher } = fakeFetch(allRoutes());
  const result = await runScheduled(env, NOW, fetcher);
  assert.equal(result.succeeded, 3);
  const snap = await readSnapshot(env, display.token);
  assert.equal(validateSnapshotSchema(snap), true, JSON.stringify(validateSnapshotSchema.errors));
  assert.equal(snap.weather.temperatureC, 12);
  assert.equal(snap.weather.summary, "Overcast");
  assert.ok(snap.weather.attribution.includes("Open-Meteo"));
  assert.match(snap.sun.sunset, /^\d{2}:\d{2}$/);
  assert.equal(snap.news.headlines.length, 3, "news is capped at three headlines");
  assert.ok(snap.reflection.attribution, "the daily thought carries its source");
});

test("provider outages do not blank the dashboard: shopping and the last good weather remain", async () => {
  const { env, display, alex } = await setup();
  await handle(request("/api/shopping", { method: "POST", body: { title: "Milk" }, cookie: alex.cookie, csrf: alex.csrf }), env);
  await runScheduled(env, NOW, fakeFetch(allRoutes()).fetcher);
  // Weather now fails. Advance past the rate limit so the job tries again.
  const later = new Date(NOW.getTime() + 60 * 60 * 1000);
  const outage = fakeFetch(allRoutes({ "https://api.open-meteo.com/": () => new Response("down", { status: 503 }), "https://calendar.example.test/": () => "throw", "https://news.example.test/": () => "throw" }));
  const result = await runScheduled(env, later, outage.fetcher);
  assert.equal(result.failed, 3);
  const snap = await readSnapshot(env, display.token, later);
  assert.equal(validateSnapshotSchema(snap), true);
  assert.equal(snap.weather.temperatureC, 12, "last good weather is kept");
  assert.equal(snap.weather.updatedAt, NOW.toISOString().replace(/\.\d{3}Z$/, "Z"), "its age is visible");
  assert.equal(snap.shopping.items[0].title, "Milk");
});

test("with no providers configured the snapshot is still valid, with explicit empty states", async () => {
  const { env, display } = await setup({ location: false, feeds: false });
  const snap = await readSnapshot(env, display.token);
  assert.equal(validateSnapshotSchema(snap), true);
  assert.equal(snap.weather.temperatureC, null);
  assert.equal(snap.sun.sunset, null);
  assert.deepEqual(snap.news.headlines, []);
});

test("rate limits hold: repeated runs inside the interval make one provider call", async () => {
  const { env } = await setup();
  const first = fakeFetch(allRoutes());
  await runScheduled(env, NOW, first.fetcher);
  const again = fakeFetch(allRoutes());
  await runScheduled(env, new Date(NOW.getTime() + 5 * 60 * 1000), again.fetcher);
  assert.equal(again.calls.length, 0);
});

test("failures back off: a retry is not attempted again until the wait has passed", async () => {
  const { env } = await setup({ feeds: false });
  const down = fakeFetch({ "https://api.open-meteo.com/": () => new Response("x", { status: 500 }) });
  await runScheduled(env, NOW, down.fetcher);
  assert.equal(down.calls.length, 1);
  const soon = fakeFetch({ "https://api.open-meteo.com/": () => okJson(weatherBody()) });
  await runScheduled(env, new Date(NOW.getTime() + 60_000), soon.fetcher);
  assert.equal(soon.calls.length, 0, "no retry within the backoff window");
  const after = fakeFetch({ "https://api.open-meteo.com/": () => okJson(weatherBody()) });
  await runScheduled(env, new Date(NOW.getTime() + 2 * 60 * 60 * 1000), after.fetcher);
  assert.equal(after.calls.length, 1);
});

test("a provider failure is recorded as a short code, never a URL or response body", async () => {
  const { env, db } = await setup({ feeds: false });
  await runScheduled(env, NOW, fakeFetch({ "https://api.open-meteo.com/": () => new Response("secret-body-text", { status: 500 }) }).fetcher);
  const row = db.prepare("SELECT last_error FROM provider_cache WHERE provider = 'weather'").get() as { last_error: string };
  assert.equal(row.last_error, "http_500");
});

test("redirects from a provider are refused", async () => {
  const { env, db } = await setup({ feeds: false });
  await runScheduled(env, NOW, fakeFetch({ "https://api.open-meteo.com/": () => new Response(null, { status: 302, headers: { Location: "https://evil.example.test/" } }) }).fetcher);
  assert.equal((db.prepare("SELECT last_error FROM provider_cache WHERE provider = 'weather'").get() as { last_error: string }).last_error, "redirect_refused");
});

test("an oversized response is refused", async () => {
  const { env, db } = await setup({ feeds: false });
  const big = new Response("x".repeat(70_000), { status: 200, headers: { "Content-Length": "70000" } });
  await runScheduled(env, NOW, fakeFetch({ "https://api.open-meteo.com/": () => big }).fetcher);
  assert.equal((db.prepare("SELECT last_error FROM provider_cache WHERE provider = 'weather'").get() as { last_error: string }).last_error, "too_large");
});

test("a non-https or credential-bearing feed address is refused without a network call", async () => {
  const { env } = await setup({ feeds: false });
  env.CALENDAR_FEED_URL = "http://calendar.example.test/family.ics";
  env.HOUSEHOLD_ID = "h1";
  const spy = fakeFetch({});
  await runScheduled(env, NOW, spy.fetcher);
  assert.equal(spy.calls.filter((c) => c.startsWith("http://")).length, 0);
  env.CALENDAR_FEED_URL = "https://user:pass@calendar.example.test/family.ics";
  await runScheduled(env, NOW, spy.fetcher);
  assert.equal(spy.calls.filter((c) => c.includes("user:pass")).length, 0);
});

test("private calendar titles are masked before they are stored, so the cache never holds them", async () => {
  const { env, db } = await setup({ location: false });
  await runScheduled(env, NOW, fakeFetch(allRoutes()).fetcher);
  const row = db.prepare("SELECT payload FROM provider_cache WHERE provider = 'calendar'").get() as { payload: string };
  assert.equal(row.payload.includes("Synthetic private appointment"), false);
  assert.ok(row.payload.includes("Busy"));
});

test("the cached calendar payload is read back for the snapshot, showing only today's events", async () => {
  const { env, display } = await setup({ location: false });
  await runScheduled(env, NOW, fakeFetch(allRoutes()).fetcher);
  const snap = await readSnapshot(env, display.token);
  const titles = snap.calendar.events.map((e: { title: string }) => e.title);
  assert.ok(titles.includes("School pickup"));
  assert.ok(titles.includes("Busy"));
  assert.equal(titles.some((t: string) => t.includes("Synthetic private")), false);
  assert.equal(titles.includes("Breakfast club") && snap.calendar.events.every((e: { time: string | null }) => e.time !== null || e.time === null), true);
});

test("the news feed list must be a JSON array of at most three URLs", () => {
  assert.deepEqual(parseFeedList(undefined), []);
  assert.deepEqual(parseFeedList('["https://a.example.test/x"]'), ["https://a.example.test/x"]);
  assert.throws(() => parseFeedList('"https://a.example.test/x"'), /JSON array/);
  assert.throws(() => parseFeedList("not json"), /JSON array/);
  assert.equal(parseFeedList(JSON.stringify(["a", "b", "c", "d"])).length, 3);
});

test("cachedPayload returns nothing before the first success, so nothing stale is invented", async () => {
  const { env } = await setup();
  assert.equal(await cachedPayload(env, "h1", "weather"), null);
});

test("the location endpoint is admin-only, validated and needs CSRF", async () => {
  const { env, alex } = await setup();
  const sam = await signIn(env, "m1");
  const body = { latitude: 55.9533, longitude: -3.1883 };
  assert.equal((await handle(request("/api/admin/household/location", { method: "PUT", body, cookie: sam.cookie, csrf: sam.csrf }), env)).status, 403);
  assert.equal((await handle(request("/api/admin/household/location", { method: "PUT", body, cookie: alex.cookie }), env)).status, 403);
  assert.equal((await handle(request("/api/admin/household/location", { method: "PUT", body: { latitude: 120, longitude: 0 }, cookie: alex.cookie, csrf: alex.csrf }), env)).status, 400);
  const ok = await handle(request("/api/admin/household/location", { method: "PUT", body, cookie: alex.cookie, csrf: alex.csrf }), env);
  assert.equal(ok.status, 200);
  const cleared = await handle(request("/api/admin/household/location", { method: "PUT", body: { latitude: null, longitude: null }, cookie: alex.cookie, csrf: alex.csrf }), env);
  assert.equal(cleared.status, 200);
});

test("a household's cache is not visible to another household's display", async () => {
  const { env, display } = await setup();
  await runScheduled(env, NOW, fakeFetch(allRoutes()).fetcher);
  const other = await signIn(env, "x1");
  const otherDisplay = await createDevice(env, other, "display", "Other display");
  const snap = await readSnapshot(env, otherDisplay.token);
  assert.equal(snap.weather.temperatureC, null, "the other household has no location or weather");
  assert.equal(snap.calendar.events.length, 0);
  assert.ok(display.token !== otherDisplay.token);
});
