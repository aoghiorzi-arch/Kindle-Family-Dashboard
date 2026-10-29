import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expandCalendar, zonedToUtc } from "../src/calendar.ts";

const fixture = (name: string) => readFileSync(fileURLToPath(new URL(`./fixtures/calendar/${name}`, import.meta.url)), "utf8");
// London is on GMT after the clocks went back on 25 October, so London midnight is 00:00 UTC.
const DAY_FROM = new Date("2026-10-29T00:00:00Z");
const DAY_TO = new Date("2026-10-30T00:00:00Z");
const WEEK_TO = new Date("2026-11-13T00:00:00Z");

test("a recurring series expands to each occurrence, in UTC, at the right local time", () => {
  const { events } = expandCalendar(fixture("basic.ics"), DAY_FROM, WEEK_TO, "Europe/London");
  const pickups = events.filter((e) => e.title === "School pickup").map((e) => e.startUtc);
  assert.deepEqual(pickups, ["2026-10-29T15:00:00.000Z", "2026-11-05T15:00:00.000Z", "2026-11-12T15:00:00.000Z"]);
});

test("private events carry the neutral label, never their title", () => {
  const { events } = expandCalendar(fixture("basic.ics"), DAY_FROM, DAY_TO, "Europe/London");
  const priv = events.find((e) => e.private);
  assert.ok(priv);
  assert.equal(priv.title, "Busy");
  assert.equal(events.some((e) => e.title.includes("Synthetic private")), false);
});

test("an all-day event is marked allDay and starts at household-local midnight", () => {
  const { events } = expandCalendar(fixture("basic.ics"), DAY_FROM, DAY_TO, "Europe/London");
  const allDay = events.find((e) => e.title === "Family day");
  assert.ok(allDay);
  assert.equal(allDay.allDay, true);
  assert.equal(allDay.startUtc, "2026-10-29T00:00:00.000Z");
});

test("an excluded occurrence is left out of the series", () => {
  const { events } = expandCalendar(fixture("basic.ics"), new Date("2026-10-29T00:00:00Z"), new Date("2026-11-03T00:00:00Z"), "Europe/London");
  const breakfast = events.filter((e) => e.title === "Breakfast club").map((e) => e.startUtc);
  assert.equal(breakfast.includes("2026-10-30T07:00:00.000Z"), false);
  assert.ok(breakfast.includes("2026-10-29T07:00:00.000Z"));
});

test("a series with a moved occurrence is skipped whole, not shown at the wrong time", () => {
  const { events, skipped } = expandCalendar(fixture("basic.ics"), DAY_FROM, DAY_TO, "Europe/London");
  assert.equal(events.some((e) => e.title === "Moved meeting"), false);
  assert.ok(skipped >= 2, `skipped ${skipped}`);
});

test("an unknown time zone is skipped and counted, not guessed", () => {
  const { events, skipped } = expandCalendar(fixture("basic.ics"), DAY_FROM, DAY_TO, "Europe/London");
  assert.equal(events.some((e) => e.title === "Unknown zone"), false);
  assert.ok(skipped >= 1);
});

test("a floating time is read as household local time", () => {
  const { events } = expandCalendar(fixture("floating.ics"), DAY_FROM, DAY_TO, "Europe/London");
  // 09:00 London on 29 October is GMT, so 09:00 UTC.
  assert.equal(events[0].startUtc, "2026-10-29T09:00:00.000Z");
});

test("events outside the window are excluded", () => {
  const { events } = expandCalendar(fixture("basic.ics"), new Date("2026-12-01T00:00:00Z"), new Date("2026-12-02T00:00:00Z"), "Europe/London");
  assert.equal(events.length, 0);
});

test("oversized feeds are refused", () => {
  const huge = "X".repeat(2_000_001);
  assert.throws(() => expandCalendar(huge, DAY_FROM, DAY_TO, "Europe/London"), /too large/);
});

test("zonedToUtc follows the zone's offset on the given date", () => {
  assert.equal(zonedToUtc(2026, 6, 21, 12, 0, 0, "Europe/London").toISOString(), "2026-06-21T11:00:00.000Z");
  assert.equal(zonedToUtc(2026, 12, 21, 12, 0, 0, "Europe/London").toISOString(), "2026-12-21T12:00:00.000Z");
});
