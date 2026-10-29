import { test } from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import { MIGRATION, openDatabase } from "./helpers.ts";

const TABLES = ["api_tokens", "devices", "households", "members", "provider_cache", "sessions", "shopping_items"];

function tables(db: DatabaseSync): string[] {
  return (db.prepare("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name").all() as { name: string }[])
    .map((row) => row.name);
}

test("migration creates the expected tables", () => {
  assert.deepEqual(tables(openDatabase()), TABLES);
});

test("migration is reproducible: two fresh databases have identical schema", () => {
  const schema = (db: DatabaseSync) =>
    db.prepare("SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").all();
  assert.deepEqual(schema(openDatabase()), schema(openDatabase()));
});

test("migration file is not duplicated or applied twice by accident", () => {
  const text = readFileSync(MIGRATION, "utf8");
  assert.equal((text.match(/CREATE TABLE shopping_items/g) ?? []).length, 1);
  assert.throws(() => openDatabase().exec(readFileSync(MIGRATION, "utf8")));
});

test("schema rejects titles over 60 characters and invalid enum values", () => {
  const db = openDatabase();
  db.prepare("INSERT INTO households (id, name, timezone, created_at) VALUES ('h', 'n', 'Europe/London', 't')").run();
  assert.throws(() =>
    db.prepare("INSERT INTO shopping_items (id, household_id, title, done, position, created_at, updated_at) VALUES ('i', 'h', ?, 0, 0, 't', 't')")
      .run("x".repeat(61)),
  );
  assert.throws(() =>
    db.prepare("INSERT INTO members (id, household_id, display_name, role, created_at) VALUES ('m', 'h', 'n', 'owner', 't')").run(),
  );
});
