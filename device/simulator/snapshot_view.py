"""Desktop 600x800 preview of a contract v1 snapshot, using the existing Today renderer.

The renderer draws only the shopping count and the first three events, plus "+N more"
text. Overflow and remaining counts are therefore passed as placeholder entries, which
are counted but never drawn. News and the clock are not drawn yet: the Today layout
predates them. Both are left for the device renderer (Phase 6) and are noted in
device/simulator/README.md.
"""
import json
from pathlib import Path

from app import render
from packages.contracts.validate import parse_utc, validation_errors

SUPPORTED_SCHEMA_VERSION = 1


def load_snapshot(path):
    doc = json.loads(Path(path).read_text())
    errors = validation_errors(doc)
    if errors:
        raise ValueError("invalid snapshot: " + "; ".join(errors))
    return doc


def to_render_data(snapshot):
    """Map a validated snapshot onto the dict shape that app.render.render() expects."""
    if snapshot["schemaVersion"] != SUPPORTED_SCHEMA_VERSION:
        raise ValueError("unsupported schemaVersion")
    generated = parse_utc(snapshot["generatedAt"])
    weather = snapshot["weather"]
    age = None
    if weather["updatedAt"] is not None:
        age = int((generated - parse_utc(weather["updatedAt"])).total_seconds() // 60)

    calendar = snapshot["calendar"]
    events = [{"title": e["title"], "time": e["time"] or "", "private": e["private"]}
              for e in calendar["events"]]
    events += [{"title": "", "time": "", "private": False}] * calendar["overflow"]

    shopping = snapshot["shopping"]
    items = [{"title": i["title"], "done": False} for i in shopping["items"]]
    items += [{"title": "", "done": False}] * max(0, shopping["remainingCount"] - len(items))

    reflection = snapshot["reflection"]
    return {
        "date": snapshot["localDate"],
        "weather": {
            "temperature": weather["temperatureC"],
            "condition": weather["summary"] or "Weather unavailable",
            "sunset": snapshot["sun"]["sunset"] or "—",
            "age_minutes": age,
        },
        "events": events,
        "shopping": items,
        "quote": {"text": reflection["text"] or "", "attribution": reflection["attribution"] or ""},
    }


def save_preview(snapshot, out_path):
    """Render a validated snapshot to a 600x800 PNG. Returns the save_frame summary."""
    return render.save_frame(to_render_data(snapshot), out_path)
