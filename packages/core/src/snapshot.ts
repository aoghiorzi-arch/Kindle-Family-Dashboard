// Builds the contract v1 snapshot from household state. Pure apart from hashing; performs no I/O.
import { sha256Hex } from "./tokens.ts";
import { SNAPSHOT_ITEM_LIMIT } from "./validation.ts";
import { clockTime, sunriseUtc, sunsetUtc } from "./sun.ts";
import type { Headline } from "./news.ts";
import { MAX_HEADLINES } from "./news.ts";
import type { Thought } from "./verse.ts";
import type { CalendarEvent } from "./calendar.ts";

export const SNAPSHOT_TTL_MS = 20 * 60 * 1000;
export const CALENDAR_EVENT_LIMIT = 4;
export const MODULES = ["weather", "calendar", "shopping", "reflection", "news"] as const;

export interface UncheckedItem {
  title: string;
}

export interface WeatherInput {
  temperatureC: number;
  summary: string;
  fetchedAt: string; // UTC ISO: when the provider was last read successfully
  attribution: string;
}

export interface SnapshotInput {
  now: Date;
  timezone: string;
  unchecked: UncheckedItem[];
  location?: { latitude: number; longitude: number } | null;
  weather?: WeatherInput | null;
  events?: CalendarEvent[]; // any window; only today's events are kept
  news?: Headline[];
  thought?: Thought | null;
}

export function formatUtc(date: Date): string {
  return date.toISOString().replace(/\.\d{3}Z$/, "Z");
}

// en-CA formats dates as YYYY-MM-DD, which the contract requires.
export function localDate(date: Date, timezone: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
}

function todaysEvents(events: CalendarEvent[], day: string, timezone: string) {
  const today = events
    .filter((e) => localDate(new Date(e.startUtc), timezone) === day)
    .sort((a, b) => a.startUtc.localeCompare(b.startUtc));
  const shown = today.slice(0, CALENDAR_EVENT_LIMIT).map((e) => ({
    title: e.title,
    time: e.allDay ? null : clockTime(new Date(e.startUtc), timezone),
    private: e.private,
  }));
  return { events: shown, overflow: today.length - shown.length };
}

export async function buildSnapshot(input: SnapshotInput): Promise<Record<string, unknown>> {
  const day = localDate(input.now, input.timezone);
  const items = input.unchecked.slice(0, SNAPSHOT_ITEM_LIMIT).map((item) => ({ title: item.title }));
  const remainingCount = input.unchecked.length;

  const weather = input.weather
    ? { temperatureC: input.weather.temperatureC, summary: input.weather.summary, updatedAt: formatUtc(new Date(input.weather.fetchedAt)), attribution: input.weather.attribution }
    : { temperatureC: null, summary: null, updatedAt: null, attribution: null };

  const location = input.location ?? null;
  const sun = location
    ? {
        sunrise: clockTime(sunriseUtc(day, location.latitude, location.longitude), input.timezone),
        sunset: clockTime(sunsetUtc(day, location.latitude, location.longitude), input.timezone),
      }
    : { sunrise: null, sunset: null };

  // Content without timestamps: the revision changes only when the content does.
  const content = {
    timezone: input.timezone,
    localDate: day,
    clock: { display24h: true },
    weather,
    sun,
    calendar: todaysEvents(input.events ?? [], day, input.timezone),
    shopping: { remainingCount, items, overflow: remainingCount - items.length },
    reflection: input.thought ? { text: input.thought.text, attribution: input.thought.attribution } : { text: null, attribution: null },
    news: { headlines: (input.news ?? []).slice(0, MAX_HEADLINES).map((h) => ({ title: h.title, source: h.source })) },
    modules: [...MODULES],
  };
  const revision = (await sha256Hex(JSON.stringify(content))).slice(0, 32);
  return {
    schemaVersion: 1,
    revision,
    generatedAt: formatUtc(input.now),
    expiresAt: formatUtc(new Date(input.now.getTime() + SNAPSHOT_TTL_MS)),
    ...content,
  };
}
