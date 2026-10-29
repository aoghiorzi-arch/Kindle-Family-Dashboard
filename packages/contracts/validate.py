"""Validate Kindle snapshots against contract v1: JSON Schema plus the checks it cannot express."""
import json
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).with_name("kindle-snapshot.v1.schema.json")


def load_schema():
    return json.loads(SCHEMA_PATH.read_text())


def parse_utc(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


def validation_errors(doc):
    """Return a sorted list of human-readable errors; an empty list means the snapshot is valid."""
    validator = Draft202012Validator(load_schema())
    errors = [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
              for e in validator.iter_errors(doc)]
    if not errors:
        if parse_utc(doc["expiresAt"]) <= parse_utc(doc["generatedAt"]):
            errors.append("expiresAt: must be later than generatedAt")
        if doc["weather"]["updatedAt"] and parse_utc(doc["weather"]["updatedAt"]) > parse_utc(doc["generatedAt"]):
            errors.append("weather/updatedAt: must not be later than generatedAt")
    return sorted(errors)
