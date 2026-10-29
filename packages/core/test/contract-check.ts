// Validates a snapshot against the shared contract schema, using the same Ajv setup as the Worker tests.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";

const schema = JSON.parse(readFileSync(fileURLToPath(new URL("../../../packages/contracts/kindle-snapshot.v1.schema.json", import.meta.url)), "utf8"));
const validate = new Ajv2020({ allErrors: true, strict: false }).compile(schema);

export function validationErrorsForTest(doc: unknown): string[] {
  return validate(doc) ? [] : (validate.errors ?? []).map((e) => `${e.instancePath} ${e.message}`);
}
