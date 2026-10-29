// Read-only calendar feed expansion (iCalendar, RFC 5545) for a time window. Uses ical.js (MPL-2.0).
// Limits: 500 occurrences per series. Moved and cancelled occurrences (RECURRENCE-ID) are applied. A series with an occurrence in an unknown time zone is skipped and counted.
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

interface Override {
  startUtc: string;
  allDay: boolean;
  title: string;
  private: boolean;
  cancelled: boolean;
  inWindowOnly: boolean; // used only if no series occurrence matched it
}

export function expandCalendar(text: string, from: Date, to: Date, householdTimezone: string): ExpandResult {
  if (new TextEncoder().encode(text).length > MAX_FEED_BYTES) throw new Error("calendar: feed too large");
  const root = new ICAL.Component(ICAL.parse(text));
  const events: CalendarEvent[] = [];
  let skipped = 0;
  const components = root.getAllSubcomponents("vevent");

  // Resolves a DTSTART or RECURRENCE-ID value to a UTC instant, or null when its zone is unknown.
  const instantOf = (component: InstanceType<typeof ICAL.Component>, property: "dtstart" | "recurrence-id", allDay: boolean): Date | null => {
    const prop = component.getFirstProperty(property);
    if (!prop) return null;
    const tzid = prop.getParameter("tzid") as string | undefined;
    if (tzid && !isZoneKnown(tzid)) return null;
    const time = prop.getFirstValue() as InstanceType<typeof ICAL.Time>;
    if (allDay) return zonedToUtc(time.year, time.month, time.day, 0, 0, 0, householdTimezone);
    if (time.zone?.tzid === "floating" && !tzid) {
      return zonedToUtc(time.year, time.month, time.day, time.hour, time.minute, time.second, householdTimezone);
    }
    return time.toJSDate();
  };
  const isAllDay = (component: InstanceType<typeof ICAL.Component>) => {
    const start = component.getFirstProperty("dtstart");
    return start?.getParameter("value") === "DATE" || (start?.getFirstValue() as InstanceType<typeof ICAL.Time> | undefined)?.isDate === true;
  };
  const isPrivateComponent = (component: InstanceType<typeof ICAL.Component>) =>
    ["PRIVATE", "CONFIDENTIAL"].includes(String(component.getFirstPropertyValue("class") ?? "").toUpperCase());

  // Pass 1: moved or cancelled occurrences, keyed by series UID and original start.
  const overrides = new Map<string, Map<string, Override>>();
  const unresolvableSeries = new Set<string>();
  for (const component of components.filter((c) => c.hasProperty("recurrence-id"))) {
    const uid = String(component.getFirstPropertyValue("uid"));
    const allDay = isAllDay(component);
    const original = instantOf(component, "recurrence-id", allDay);
    const start = instantOf(component, "dtstart", allDay);
    if (!original || !start) {
      unresolvableSeries.add(uid);
      continue;
    }
    const isPrivate = isPrivateComponent(component);
    const series = overrides.get(uid) ?? new Map<string, Override>();
    series.set(original.toISOString(), {
      startUtc: start.toISOString(),
      allDay,
      title: isPrivate ? "Busy" : cleanTitle(component.getFirstPropertyValue("summary") as string),
      private: isPrivate,
      cancelled: String(component.getFirstPropertyValue("status") ?? "").toUpperCase() === "CANCELLED",
      inWindowOnly: true,
    });
    overrides.set(uid, series);
  }

  // Pass 2: the master events.
  for (const component of components.filter((c) => !c.hasProperty("recurrence-id"))) {
    const uid = String(component.getFirstPropertyValue("uid"));
    if (unresolvableSeries.has(uid)) {
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
    if (tzid && !isZoneKnown(tzid)) {
      skipped += 1;
      continue;
    }
    const allDay = isAllDay(component);
    const isPrivate = isPrivateComponent(component);
    const title = isPrivate ? "Busy" : cleanTitle(event.summary);
    const seriesOverrides = overrides.get(uid) ?? new Map<string, Override>();
    const emitted = new Set<string>();

    const emit = (startUtc: Date | string, eventTitle: string, eventPrivate: boolean, eventAllDay: boolean) => {
      const at = typeof startUtc === "string" ? new Date(startUtc) : startUtc;
      if (at >= from && at < to) events.push({ startUtc: at.toISOString(), allDay: eventAllDay, title: eventTitle, private: eventPrivate });
    };

    if (!event.isRecurring()) {
      const instant = instantOf(component, "dtstart", allDay);
      const override = instant ? seriesOverrides.get(instant.toISOString()) : undefined;
      if (override) {
        if (!override.cancelled) emit(override.startUtc, override.title, override.private, override.allDay);
        // Overrides handled here are not emitted again below.
        seriesOverrides.delete(instant!.toISOString());
      } else if (instant) {
        emit(instant, title, isPrivate, allDay);
      }
      // A single event that was moved from before the window still shows at its new time.
      for (const [key, moved] of seriesOverrides) {
        if (!moved.cancelled) emit(moved.startUtc, moved.title, moved.private, moved.allDay);
        seriesOverrides.delete(key);
      }
      continue;
    }

    const iterator = event.iterator();
    let count = 0;
    for (let next = iterator.next(); next && count < MAX_OCCURRENCES; next = iterator.next()) {
      count += 1;
      const original = (() => {
        const time = next as InstanceType<typeof ICAL.Time>;
        if (allDay) return zonedToUtc(time.year, time.month, time.day, 0, 0, 0, householdTimezone);
        if (time.zone?.tzid === "floating" && !tzid) {
          return zonedToUtc(time.year, time.month, time.day, time.hour, time.minute, time.second, householdTimezone);
        }
        return time.toJSDate();
      })();
      const override = seriesOverrides.get(original.toISOString());
      if (override) {
        emitted.add(original.toISOString());
        if (override.cancelled) continue;
        emit(override.startUtc, override.title, override.private, override.allDay);
        continue;
      }
      if (original >= to) break;
      emit(original, title, isPrivate, allDay);
    }

    // Moved occurrences whose original start the expansion did not reach (for example, an earlier occurrence moved into the window).
    for (const [key, override] of seriesOverrides) {
      if (emitted.has(key) || override.cancelled) continue;
      emit(override.startUtc, override.title, override.private, override.allDay);
    }
  }

  events.sort((a, b) => a.startUtc.localeCompare(b.startUtc));
  return { events, skipped };
}
