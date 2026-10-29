// Headlines from RSS 2.0 or Atom feeds. Titles only: no excerpts or article bodies are stored.
// Uses fast-xml-parser (MIT). Each source's title is kept as the attribution shown beside a headline.
import { XMLParser } from "fast-xml-parser";

export const MAX_HEADLINES = 3;
export const MAX_TITLE = 60;
export const MAX_SOURCE = 40;

export interface Headline {
  title: string;
  source: string;
}

const parser = new XMLParser({ ignoreAttributes: false, removeNSPrefix: true, processEntities: false, parseTagValue: false });

function text(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number") return String(value);
  if (value && typeof value === "object" && "#text" in value) return text((value as { "#text": unknown })["#text"]);
  return "";
}

const ENTITIES: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", "#39": "'" };

function clean(value: string, max: number): string {
  const stripped = value
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/<[^>]*>/g, " ")
    .replace(/&(#39|amp|lt|gt|quot|apos);/g, (_, name: string) => ENTITIES[name])
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const chars = [...stripped];
  return chars.length > max ? `${chars.slice(0, max - 1).join("")}…` : stripped;
}

function asArray<T>(value: T | T[] | undefined): T[] {
  if (value === undefined) return [];
  return Array.isArray(value) ? value : [value];
}

export function parseHeadlines(xml: string): Headline[] {
  const doc = parser.parse(xml) as Record<string, unknown>;
  const rss = doc.rss as { channel?: { title?: unknown; item?: unknown } } | undefined;
  const atom = doc.feed as { title?: unknown; entry?: unknown } | undefined;
  if (rss?.channel) {
    const source = clean(text(rss.channel.title), MAX_SOURCE) || "News";
    return asArray(rss.channel.item as Record<string, unknown>[])
      .map((item) => ({ title: clean(text(item.title), MAX_TITLE), source }))
      .filter((h) => h.title.length > 0);
  }
  if (atom) {
    const source = clean(text(atom.title), MAX_SOURCE) || "News";
    return asArray(atom.entry as Record<string, unknown>[])
      .map((entry) => ({ title: clean(text(entry.title), MAX_TITLE), source }))
      .filter((h) => h.title.length > 0);
  }
  throw new Error("news: not an RSS or Atom feed");
}

export function limitHeadlines(lists: Headline[][]): Headline[] {
  return lists.flat().slice(0, MAX_HEADLINES);
}
