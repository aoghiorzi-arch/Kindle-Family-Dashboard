"""Contract v1: valid fixtures pass; invalid fixtures are refused for the expected reason."""
import json
import unittest
from pathlib import Path

from packages.contracts.validate import load_schema, validation_errors

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "snapshots"
VALID = sorted((FIXTURES / "valid").glob("*.json"))
INVALID = sorted((FIXTURES / "invalid").glob("*.json"))

# Each invalid fixture must fail with an error mentioning this text.
EXPECTED = {
    "title-too-long": "too long",
    "wrong-version": "schemaVersion",
    "extra-token-field": "Additional properties",
    "private-leak": "Busy",
    "too-many-events": "too long",
    "bad-time": "does not match",
    "bad-timezone": "does not match",
    "too-many-shopping-items": "too long",
    "missing-weather-block": "weather",
    "expiry-before-generation": "expiresAt",
}


class SnapshotContractTests(unittest.TestCase):
    def test_schema_is_draft_2020_12_and_v1(self):
        schema = load_schema()
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], 1)
        self.assertFalse(schema["additionalProperties"])

    def test_fixture_sets_are_present(self):
        self.assertGreaterEqual(len(VALID), 5)
        self.assertEqual(sorted(p.stem for p in INVALID), sorted(EXPECTED))

    def test_valid_fixtures_pass(self):
        for path in VALID:
            with self.subTest(fixture=path.name):
                self.assertEqual(validation_errors(json.loads(path.read_text())), [])

    def test_invalid_fixtures_fail_for_the_expected_reason(self):
        for path in INVALID:
            with self.subTest(fixture=path.name):
                errors = validation_errors(json.loads(path.read_text()))
                self.assertTrue(errors, "fixture unexpectedly valid")
                self.assertTrue(
                    any(EXPECTED[path.stem] in e for e in errors),
                    f"expected {EXPECTED[path.stem]!r} in {errors}",
                )

    def test_private_events_must_be_labelled_busy(self):
        doc = json.loads((FIXTURES / "valid" / "full.json").read_text())
        for event in doc["calendar"]["events"]:
            if event["private"]:
                self.assertEqual(event["title"], "Busy")

    def test_no_credential_like_fields_in_valid_fixtures(self):
        forbidden = ("token", "secret", "url", "password", "key")
        for path in VALID:
            text = path.read_text().lower()
            for word in forbidden:
                with self.subTest(fixture=path.name, word=word):
                    self.assertNotIn(f'"{word}', text)


if __name__ == "__main__":
    unittest.main()
