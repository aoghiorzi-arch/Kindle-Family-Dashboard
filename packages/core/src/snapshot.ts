// Builds a contract v1 snapshot from household state. Pure apart from hashing; no I/O.
import { sha256Hex } from "./tokens.ts";
import { SNAPSHOT_ITEM_LIMIT } from "./validation.ts";

export const SNAPSHOT_TTL_MS = 20 * 60 * 1000;

export interface UncheckedItem {
  title: string;
}

export interface SnapshotInput {
  now: Date;
  timezone: string;
  unchecked: UncheckedItem[]; // all unchecked items in list order
}

export function formatUtc(date: Date): string {
  return date.toISOString().replace(/\.\d{3}Z$/, "Z");
}

// en-CA formats dates as YYYY-MM-DD, which is what the contract requires.
export function localDate(date: Date, timezone: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

export async function buildSnapshot(input: SnapshotInput): Promise<Record<string, unknown>> {
  const items = input.unchecked.slice(0, SNAPSHOT_ITEM_LIMIT).map((item) => ({ title: item.title }));
  const remainingCount = input.unchecked.length;

  // Content without timestamps: the revision changes only when the content does.
  const content = {
    timezone: input.timezone,
    localDate: localDate(input.now, input.timezone),
    clock: { display24h: true },
    weather: { temperatureC: null, summary: null, updatedAt: null },
    sun: { sunrise: null, sunset: null },
    calendar: { events: [], overflow: 0 },
    shopping: { remainingCount, items, overflow: remainingCount - items.length },
    reflection: { text: null, attribution: null },
    news: { headlines: [] },
    modules: ["shopping"],
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
