"""Simulator: every valid fixture renders 600x800; private titles never reach the renderer."""
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from device.simulator.snapshot_view import load_snapshot, save_preview, to_render_data

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "snapshots" / "valid"


class SnapshotSimulatorTests(unittest.TestCase):
    def test_every_valid_fixture_renders_600x800(self):
        with tempfile.TemporaryDirectory() as tmp:
            for path in sorted(FIXTURES.glob("*.json")):
                with self.subTest(fixture=path.name):
                    out = Path(tmp) / f"{path.stem}.png"
                    save_preview(load_snapshot(path), out)
                    with Image.open(out) as im:
                        self.assertEqual(im.size, (600, 800))

    def test_rendering_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.png", Path(tmp) / "b.png"
            snap = load_snapshot(FIXTURES / "full.json")
            self.assertEqual(save_preview(snap, a)["sha256"], save_preview(snap, b)["sha256"])

    def test_private_event_title_is_masked_before_rendering(self):
        doc = json.loads((FIXTURES / "private-only.json").read_text())
        data = to_render_data(load_snapshot(FIXTURES / "private-only.json"))
        self.assertEqual(data["events"][0]["title"], "Busy")
        self.assertTrue(data["events"][0]["private"])
        self.assertNotIn("Dentist", json.dumps(data))

    def test_stale_weather_age_is_computed_from_generated_time(self):
        data = to_render_data(load_snapshot(FIXTURES / "stale-weather.json"))
        self.assertEqual(data["weather"]["age_minutes"], 3 * 24 * 60 + 2 * 60)

    def test_empty_snapshot_uses_explicit_empty_states(self):
        data = to_render_data(load_snapshot(FIXTURES / "empty.json"))
        self.assertEqual(data["weather"]["condition"], "Weather unavailable")
        self.assertIsNone(data["weather"]["temperature"])
        self.assertEqual(data["weather"]["sunset"], "—")
        self.assertEqual(data["events"], [])
        self.assertEqual(data["shopping"], [])

    def test_overflow_counts_reach_the_renderer(self):
        data = to_render_data(load_snapshot(FIXTURES / "long.json"))
        self.assertEqual(len(data["events"]), 4 + 12)
        self.assertEqual(len(data["shopping"]), 19)

    def test_invalid_snapshot_is_refused(self):
        bad = Path(__file__).resolve().parent / "fixtures" / "snapshots" / "invalid" / "private-leak.json"
        with self.assertRaises(ValueError):
            load_snapshot(bad)


if __name__ == "__main__":
    unittest.main()
