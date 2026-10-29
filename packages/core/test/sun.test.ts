import { test } from "node:test";
import assert from "node:assert/strict";
import { clockTime, sunriseUtc, sunsetUtc } from "../src/sun.ts";

// Reference times. Sunset: the Python implementation (app/solar.py). Sunrise and both
// sunsets: the independent astronomy library astral 3.2, which the Python value agrees with to within a minute.
const REFERENCE = [
  { day: "2026-10-29", lat: 51.5074, lon: -0.1278, tz: "Europe/London", sunset: "16:40", sunrise: "06:48" },
  { day: "2026-06-21", lat: 51.5074, lon: -0.1278, tz: "Europe/London", sunset: "21:21", sunrise: "04:43" },
  { day: "2026-12-21", lat: 55.9533, lon: -3.1883, tz: "Europe/London", sunset: "15:39", sunrise: "08:42" },
  { day: "2026-03-20", lat: 40.7128, lon: -74.006, tz: "America/New_York", sunset: "19:07", sunrise: "06:59" },
  { day: "2026-10-29", lat: -33.8688, lon: 151.2093, tz: "Australia/Sydney", sunset: "19:19", sunrise: "05:58" },
  { day: "2026-10-29", lat: 35.6762, lon: 139.6503, tz: "Asia/Tokyo", sunset: "16:50", sunrise: "06:00" },
];

function minutesOf(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}

test("sunset matches the reference values to within one minute", () => {
  for (const c of REFERENCE) {
    const got = clockTime(sunsetUtc(c.day, c.lat, c.lon), c.tz);
    assert.ok(got, `no sunset for ${c.day} ${c.tz}`);
    assert.ok(Math.abs(minutesOf(got) - minutesOf(c.sunset)) <= 1, `${c.day} ${c.tz}: got ${got}, expected ${c.sunset}`);
  }
});

test("sunrise matches the reference values to within one minute", () => {
  for (const c of REFERENCE) {
    const got = clockTime(sunriseUtc(c.day, c.lat, c.lon), c.tz);
    assert.ok(got, `no sunrise for ${c.day} ${c.tz}`);
    assert.ok(Math.abs(minutesOf(got) - minutesOf(c.sunrise)) <= 1, `${c.day} ${c.tz}: got ${got}, expected ${c.sunrise}`);
  }
});

test("sunrise comes before sunset on the same day, with plausible daylight length (6.5 to 18 hours)", () => {
  for (const c of REFERENCE) {
    const rise = sunriseUtc(c.day, c.lat, c.lon);
    const set = sunsetUtc(c.day, c.lat, c.lon);
    assert.ok(rise && set);
    const hours = (set.getTime() - rise.getTime()) / 3_600_000;
    assert.ok(hours > 6.5 && hours < 18, `${c.day} ${c.tz}: ${hours.toFixed(2)} h of daylight`);
  }
});

test("London sunrise on 29 October falls in the early morning", () => {
  const rise = clockTime(sunriseUtc("2026-10-29", 51.5074, -0.1278), "Europe/London");
  assert.ok(rise);
  assert.ok(minutesOf(rise) >= 6 * 60 + 45 && minutesOf(rise) <= 7 * 60 + 30, rise);
});

test("polar day has no sunset", () => {
  assert.equal(sunsetUtc("2026-06-21", 78.2, 15.6), null);
});

test("times are rendered in the household zone, not UTC", () => {
  // Late October London is on GMT, the same as UTC, so use a summer date (BST).
  const set = sunsetUtc("2026-06-21", 51.5074, -0.1278);
  assert.ok(set);
  assert.notEqual(clockTime(set, "Europe/London"), clockTime(set, "UTC"));
});
