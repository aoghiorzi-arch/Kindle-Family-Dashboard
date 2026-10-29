import { test } from "node:test";
import assert from "node:assert/strict";
import { thoughtForDate } from "../src/verse.ts";
import { WEATHER_ATTRIBUTION, openMeteoUrl, parseOpenMeteoCurrent, summaryForCode } from "../src/weather.ts";
import { limitHeadlines, parseHeadlines } from "../src/news.ts";
import { MAX_BACKOFF_MS, POLICY, nextAttemptAfterFailure, shouldAttempt } from "../src/policy.ts";
import { buildSnapshot } from "../src/snapshot.ts";
import { validationErrorsForTest } from "./contract-check.ts";

// ---- Verse: same index as app/content.py (references captured from the Python implementation)
test("the verse for a date matches the Python implementation", async () => {
  const expected: Record<string, string> = {
    "2026-10-29": "Proverbs 17:22 (KJV)",
    "2026-10-30": "Lamentations 3:23 (KJV)",
    "2026-01-01": "Colossians 3:23 (KJV)",
    "2026-06-21": "Colossians 3:23 (KJV)",
    "2026-12-31": "Proverbs 3:6 (KJV)",
  };
  for (const [day, reference] of Object.entries(expected)) {
    assert.equal((await thoughtForDate(day)).attribution, reference, day);
  }
});

test("the verse stays the same for the same day", async () => {
  assert.deepEqual(await thoughtForDate("2026-10-29"), await thoughtForDate("2026-10-29"));
});

// ---- Weather
test("a valid Open-Meteo current block is parsed to a reading", () => {
  const reading = parseOpenMeteoCurrent({ current: { time: "2026-10-29T08:00", temperature_2m: 12.4, weather_code: 3 } });
  assert.deepEqual(reading, { temperatureC: 12, summary: "Overcast", observedAt: "2026-10-29T08:00" });
});

test("bad weather payloads are refused with a short error", () => {
  const bad = [
    null,
    {},
    { current: { time: "2026-10-29T08:00", temperature_2m: "12", weather_code: 3 } },
    { current: { time: "2026-10-29T08:00", temperature_2m: 999, weather_code: 3 } },
    { current: { time: "2026-10-29T08:00", temperature_2m: 12, weather_code: 500 } },
    { current: { temperature_2m: 12, weather_code: 3 } },
  ];
  for (const body of bad) assert.throws(() => parseOpenMeteoCurrent(body), /^Error: weather:/, JSON.stringify(body));
});

test("unknown weather codes get a generic summary", () => {
  assert.equal(summaryForCode(42), "Weather");
});

test("the request asks only for the current block, in the household zone", () => {
  const url = openMeteoUrl(51.5074, -0.1278, "Europe/London");
  assert.ok(url.startsWith("https://api.open-meteo.com/v1/forecast?"));
  assert.ok(url.includes("current=temperature_2m%2Cweather_code"));
  assert.ok(url.includes("timezone=Europe%2FLondon"));
});

test("the attribution text names the source", () => {
  assert.ok(WEATHER_ATTRIBUTION.includes("Open-Meteo"));
});

// ---- News
test("RSS headlines keep titles only, the channel name as source, and decode entities", () => {
  const xml = `<?xml version="1.0"?><rss version="2.0"><channel><title>Synthetic Daily</title>
    <item><title>Library opens &amp; extends hours</title><description>Long body text that must not be stored.</description></item>
    <item><title><![CDATA[<b>Bold</b> headline]]></title></item>
  </channel></rss>`;
  const items = parseHeadlines(xml);
  assert.deepEqual(items, [
    { title: "Library opens & extends hours", source: "Synthetic Daily" },
    { title: "Bold headline", source: "Synthetic Daily" },
  ]);
  assert.equal(JSON.stringify(items).includes("Long body"), false);
});

test("Atom entries are read too", () => {
  const xml = `<feed xmlns="http://www.w3.org/2005/Atom"><title>Synthetic Atom</title>
    <entry><title>One</title></entry><entry><title>Two</title></entry></feed>`;
  assert.deepEqual(parseHeadlines(xml).map((h) => h.title), ["One", "Two"]);
});

test("long headlines are cut to 60 characters with an ellipsis", () => {
  const xml = `<rss><channel><title>S</title><item><title>${"word ".repeat(30)}</title></item></channel></rss>`;
  const [h] = parseHeadlines(xml);
  assert.equal([...h.title].length, 60);
  assert.ok(h.title.endsWith("…"));
});

test("documents that are neither RSS nor Atom are refused", () => {
  assert.throws(() => parseHeadlines("<html><body>nope</body></html>"), /not an RSS or Atom feed/);
});

test("headlines from several feeds are capped at three", () => {
  const one = (t: string) => ({ title: t, source: "S" });
  assert.equal(limitHeadlines([[one("a"), one("b")], [one("c"), one("d")]]).length, 3);
});

// ---- Cache and rate-limit policy
test("no record, or an expired one, allows a fetch; a fresh one does not", () => {
  const now = new Date("2026-10-29T08:00:00Z");
  assert.equal(shouldAttempt(null, "weather", now), true);
  const fresh = { fetchedAt: "2026-10-29T07:45:00Z", nextAttemptAt: null };
  assert.equal(shouldAttempt(fresh, "weather", now), false);
  const old = { fetchedAt: "2026-10-29T07:00:00Z", nextAttemptAt: null };
  assert.equal(shouldAttempt(old, "weather", now), true);
});

test("the rate limit holds even when the data is stale", () => {
  const now = new Date("2026-10-29T08:00:00Z");
  const waiting = { fetchedAt: "2026-10-29T07:00:00Z", nextAttemptAt: "2026-10-29T08:05:00Z" };
  assert.equal(shouldAttempt(waiting, "weather", now), false);
});

test("failures back off by doubling, capped at one hour", () => {
  const now = new Date("2026-10-29T08:00:00Z");
  const minutesAfter = (failures: number) => (nextAttemptAfterFailure("weather", failures, now).getTime() - now.getTime()) / 60000;
  assert.equal(minutesAfter(1), POLICY.weather.minIntervalMs / 60000);
  assert.equal(minutesAfter(2), 2 * POLICY.weather.minIntervalMs / 60000);
  assert.equal(minutesAfter(50), MAX_BACKOFF_MS / 60000);
});

// ---- Snapshot builder: empty and full states both produce a contract-valid document
const NOW = new Date("2026-10-29T08:00:00Z");
test("a household with no providers configured still gets a valid snapshot with explicit empty states", async () => {
  const snapshot = (await buildSnapshot({ now: NOW, timezone: "Europe/London", unchecked: [], location: null, weather: null, events: [], news: [], thought: null })) as Record<string, any>;
  assert.deepEqual(snapshot.weather, { temperatureC: null, summary: null, updatedAt: null, attribution: null });
  assert.deepEqual(snapshot.sun, { sunrise: null, sunset: null });
  assert.deepEqual(snapshot.calendar, { events: [], overflow: 0 });
  assert.deepEqual(snapshot.news, { headlines: [] });
  assert.deepEqual(snapshot.reflection, { text: null, attribution: null });
  assert.deepEqual(validationErrorsForTest(snapshot), []);
});

test("a fully populated snapshot carries sun times, today's events only, masked privates and attribution", async () => {
  const snapshot = (await buildSnapshot({
    now: NOW,
    timezone: "Europe/London",
    unchecked: [{ title: "Milk" }],
    location: { latitude: 51.5074, longitude: -0.1278 },
    weather: { temperatureC: 12, summary: "Overcast", fetchedAt: "2026-10-29T07:45:00Z", attribution: WEATHER_ATTRIBUTION },
    events: [
      { startUtc: "2026-10-29T15:00:00.000Z", allDay: false, title: "School pickup", private: false },
      { startUtc: "2026-10-29T18:00:00.000Z", allDay: false, title: "Busy", private: true },
      { startUtc: "2026-10-30T09:00:00.000Z", allDay: false, title: "Tomorrow only", private: false },
      { startUtc: "2026-10-29T00:00:00.000Z", allDay: true, title: "Family day", private: false },
    ],
    news: [{ title: "Headline", source: "Synthetic" }],
    thought: { text: "Sample text", attribution: "Psalm 1:1 (KJV)" },
  })) as Record<string, any>;
  assert.deepEqual(validationErrorsForTest(snapshot), []);
  assert.equal(snapshot.weather.updatedAt, "2026-10-29T07:45:00Z");
  assert.equal(snapshot.weather.attribution, WEATHER_ATTRIBUTION);
  assert.match(snapshot.sun.sunset, /^\d{2}:\d{2}$/);
  assert.match(snapshot.sun.sunrise, /^\d{2}:\d{2}$/);
  const titles = snapshot.calendar.events.map((e: { title: string }) => e.title);
  assert.deepEqual(titles, ["Family day", "School pickup", "Busy"]);
  assert.equal(snapshot.calendar.events[0].time, null, "all-day events have no clock time");
  assert.equal(snapshot.calendar.events[1].time, "15:00");
  assert.equal(snapshot.calendar.events[2].private, true);
});

test("calendar overflow beyond four events is counted", async () => {
  const events = Array.from({ length: 6 }, (_, n) => ({ startUtc: `2026-10-29T${String(9 + n).padStart(2, "0")}:00:00.000Z`, allDay: false, title: `E${n}`, private: false }));
  const snapshot = (await buildSnapshot({ now: NOW, timezone: "Europe/London", unchecked: [], location: null, weather: null, events, news: [], thought: null })) as Record<string, any>;
  assert.equal(snapshot.calendar.events.length, 4);
  assert.equal(snapshot.calendar.overflow, 2);
});
