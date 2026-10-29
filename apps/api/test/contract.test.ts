import { test } from "node:test";
import assert from "node:assert/strict";
import { validateSnapshotSchema } from "./helpers.ts";
import { buildSnapshot } from "../../../packages/core/src/index.ts";

test("contract schema compiles under draft 2020-12", () => {
  assert.equal(typeof validateSnapshotSchema, "function");
});

test("an empty household snapshot is valid contract v1", async () => {
  const snapshot = await buildSnapshot({ now: new Date("2026-10-29T08:00:00Z"), timezone: "Europe/London", unchecked: [] });
  assert.equal(validateSnapshotSchema(snapshot), true, JSON.stringify(validateSnapshotSchema.errors));
});

test("a snapshot with more than seven items keeps the list bounded and counts the rest", async () => {
  const unchecked = Array.from({ length: 12 }, (_, n) => ({ title: `Item ${n + 1}` }));
  const snapshot = (await buildSnapshot({ now: new Date("2026-10-29T08:00:00Z"), timezone: "Europe/London", unchecked })) as {
    shopping: { remainingCount: number; items: unknown[]; overflow: number };
  };
  assert.equal(validateSnapshotSchema(snapshot), true, JSON.stringify(validateSnapshotSchema.errors));
  assert.equal(snapshot.shopping.items.length, 7);
  assert.equal(snapshot.shopping.remainingCount, 12);
  assert.equal(snapshot.shopping.overflow, 5);
});

test("localDate uses the household timezone, not UTC", async () => {
  // 23:30 UTC on 29 Oct is already 30 Oct in Tokyo.
  const snapshot = (await buildSnapshot({ now: new Date("2026-10-29T23:30:00Z"), timezone: "Asia/Tokyo", unchecked: [] })) as {
    localDate: string;
  };
  assert.equal(snapshot.localDate, "2026-10-30");
});

test("expiresAt is after generatedAt and both are UTC Z timestamps", async () => {
  const snapshot = (await buildSnapshot({ now: new Date("2026-10-29T08:00:00Z"), timezone: "Europe/London", unchecked: [] })) as {
    generatedAt: string;
    expiresAt: string;
  };
  assert.equal(snapshot.generatedAt, "2026-10-29T08:00:00Z");
  assert.equal(snapshot.expiresAt, "2026-10-29T08:20:00Z");
});
