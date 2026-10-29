// Input rules shared by every write path. Limits match the snapshot contract and the D1 schema.

export const TITLE_MAX = 60;
export const LIST_LIMIT = 200;
export const SNAPSHOT_ITEM_LIMIT = 7;

export class ValidationError extends Error {
  readonly field: string;

  constructor(field: string, message: string) {
    super(`${field} ${message}`);
    this.field = field;
  }
}

export function parseTitle(value: unknown): string {
  if (typeof value !== "string") throw new ValidationError("title", "must be a string");
  const title = value.normalize("NFC").trim();
  const length = [...title].length; // code points, as the JSON Schema counts them
  if (length < 1 || length > TITLE_MAX) throw new ValidationError("title", `must be 1 to ${TITLE_MAX} characters`);
  if (/[\u0000-\u001f\u007f]/.test(title)) throw new ValidationError("title", "must not contain control characters");
  return title;
}

export function parseOptionalBoolean(value: unknown, field: string): boolean | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "boolean") throw new ValidationError(field, "must be true or false");
  return value;
}

export function parseVersion(value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 1 || value > 1_000_000_000) {
    throw new ValidationError("version", "must be a positive integer");
  }
  return value;
}

export function parseOptionalPosition(value: unknown): number | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0 || value > 1_000_000) {
    throw new ValidationError("position", "must be an integer from 0 to 1000000");
  }
  return value;
}
