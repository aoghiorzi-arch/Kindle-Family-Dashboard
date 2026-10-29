// Read-only calendar feed expansion (iCalendar, RFC 5545) for a time window. Uses ical.js (MPL-2.0).
// Limits: 500 occurrences per series. Series with moved occurrences (RECURRENCE-ID) and unresolvable time zones are counted as skipped.
import ICAL from "ical.js";

export const MAX_FEED_BYTES = 2_000_000;
const MAX_OCCURRENCES = 500;

export interface CalendarEvent {
  startUtc: string; // ISO UTC instant
  allDay: boolean;
  title: string; // "Busy" for private events, whatever the source title
  private: boolean;
}

export interface ExpandResult {
  events: CalendarEvent[];
  skipped: number;
}

function cleanTitle(value: string | null | undefined): string {
  const text = (value ?? "").replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim();
  const chars = [...text];
  if (chars.length === 0) return "Untitled";
  return chars.length > 60 ? `${chars.slice(0, 59).join("")}…` : text;
}

// Wall-clock time in a named zone -> UTC instant, using the zone's offset at that moment.
export function zonedToUtc(year: number, month: number, day: number, hour: number, minute: number, second: number, timezone: string): Date {
  const naive = Date.UTC(year, month - 1, day, hour, minute, second);
  const offsetAt = (instant: number) => {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: timezone, hourCycle: "h23", year: "numeric", month: "numeric", day: "numeric", hour: "numeric", minute: "numeric", second: "numeric",
    }).formatToParts(new Date(instant));
    const get = (type: string) => Number(parts.find((p) => p.type === type)?.value);
    return Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"), get("second")) - instant;
  };
  const first = naive - offsetAt(naive);
  return new Date(naive - offsetAt(first));
}

function isZoneKnown(timezone: string): boolean {
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: timezone });
    return true;
  } catch {
    return false;
  }
}

export function expandCalendar(text: string, from: Date, to: Date, householdTimezone: string): ExpandResult {
  if (new TextEncoder().encode(text).length > MAX_FEED_BYTES) throw new Error("calendar: feed too large");
  const root = new ICAL.Component(ICAL.parse(text));
  const events: CalendarEvent[] = [];
  let skipped = 0;
  const components = root.getAllSubcomponents("vevent");
  // A series with any moved or changed occurrence is skipped whole: showing its original times would be wrong.
  const overridden = new Set(
    components.filter((c) => c.hasProperty("recurrence-id")).map((c) => String(c.getFirstPropertyValue("uid"))),
  );

  for (const component of components) {
    const uid = String(component.getFirstPropertyValue("uid"));
    if (component.hasProperty("recurrence-id") || overridden.has(uid)) {
      skipped += 1;
      continue;
    }
    const event = new ICAL.Event(component);
    const start = component.getFirstProperty("dtstart");
    if (!start) {
      skipped += 1;
      continue;
    }
    const tzid = start.getParameter("tzid") as string | undefined;
    const allDay = start.getParameter("value") === "DATE" || event.startDate.isDate;
    if (tzid && !isZoneKnown(tzid)) {
      skipped += 1;
      continue;
    }
    const isPrivate = ["PRIVATE", "CONFIDENTIAL"].includes(String(component.getFirstPropertyValue("class") ?? "").toUpperCase());
    const title = isPrivate ? "Busy" : cleanTitle(event.summary);

    const toInstant = (time: InstanceType<typeof ICAL.Time>): Date | null => {
      if (allDay) return zonedToUtc(time.year, time.month, time.day, 0, 0, 0, householdTimezone);
      if (time.zone?.tzid === "floating" && !tzid) {
        // Floating time (no zone): read as household local time.
        return zonedToUtc(time.year, time.month, time.day, time.hour, time.minute, time.second, householdTimezone);
      }
      return time.toJSDate();
    };

    if (!event.isRecurring()) {
      const instant = toInstant(event.startDate);
      if (instant && instant >= from && instant < to) {
        events.push({ startUtc: instant.toISOString(), allDay, title, private: isPrivate });
      }
      continue;
    }

    const iterator = event.iterator();
    let count = 0;
    for (let next = iterator.next(); next && count < MAX_OCCURRENCES; next = iterator.next()) {
      count += 1;
      const instant = toInstant(next);
      if (!instant) continue;
      if (instant >= to) break;
      if (instant >= from) events.push({ startUtc: instant.toISOString(), allDay, title, private: isPrivate });
    }
  }

  events.sort((a, b) => a.startUtc.localeCompare(b.startUtc));
  return { events, skipped };
}
