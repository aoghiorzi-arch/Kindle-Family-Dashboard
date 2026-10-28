"""Clock-controlled reliability tests; no external services or physical display."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from app import frames, render, store, weather


class FrameLifecycleTest(unittest.TestCase):
 def setUp(self):
  self.tmp = tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.db = Path(self.tmp.name) / 'family.sqlite3'
  store.init_db(self.db)
  self.conn = store.connect(self.db)
  self.addCleanup(self.conn.close)
  self.hh = store.create_household(self.conn, 'Test')
  store.set_location(self.conn, self.hh, 51.5074, -0.1278, 'Europe/London')
  self.now = datetime.fromisoformat('2026-03-29T22:59:00+00:00').timestamp()
  self.provider = weather.FakeProvider({'temperature': 12, 'condition': 'Cloudy'})
  self.service = frames.FrameService(self.db, self.provider, lambda: self.now)

 def refresh(self):
  return self.service.refresh(self.conn, self.hh)

 def test_background_checks_roll_day_and_imported_events_in_household_zone(self):
  # BST has started: midnight in London is 23:00 UTC, not the host's midnight.
  store.replace_calendar(self.conn, self.hh, [
   {'uid': 'a', 'day': '2026-03-29', 'time': '10:00', 'title': 'Sunday', 'private': False},
   {'uid': 'b', 'day': '2026-03-30', 'time': '10:00', 'title': 'Monday', 'private': False}])
  before = self.refresh()[0]
  self.now += 60
  self.service.refresh_all()  # no browser or editing request
  after = self.service.path(self.hh).read_bytes()
  self.assertNotEqual(before, after)
  block = weather.frame_weather(self.conn, self.hh, self.provider, int(self.now), '2026-03-30')
  expected = render.png_bytes(store.snapshot(self.conn, self.hh, '2026-03-30', block))
  self.assertEqual(after, expected)

 def test_unchanged_pixels_keep_file_and_hash(self):
  self.now -= 3600  # stay on the same household day during this check
  first = self.refresh()
  stat = self.service.path(self.hh).stat()
  self.now += 60
  again = self.refresh()
  self.assertEqual(first[1:], again[1:])
  self.assertEqual(stat.st_mtime_ns, self.service.path(self.hh).stat().st_mtime_ns)

 def test_weather_refreshes_without_edit_and_failed_weather_shows_age(self):
  first = self.refresh()[0]
  self.provider.sample['temperature'] = 20
  self.now += weather.MAX_AGE
  self.service.refresh_all()
  second = self.service.path(self.hh).read_bytes()
  self.assertNotEqual(first, second)
  self.now += 3 * 3600
  with patch.object(self.provider, 'fetch', side_effect=OSError('offline')):
   stale = self.refresh()
  self.assertFalse(stale[2])  # frame is fresh, its weather is old
  self.assertNotEqual(second, stale[0])
  self.assertEqual(store.get_weather(self.conn, self.hh)['fetched_at'], int(self.now - 3 * 3600))

 def test_restart_recovers_last_good_image_after_render_failure(self):
  first = self.refresh()
  self.service = frames.FrameService(self.db, self.provider, lambda: self.now)
  with patch.object(render, 'png_bytes', side_effect=RuntimeError('broken renderer')):
   fallback = self.refresh()
  self.assertEqual(first[:2], fallback[:2])
  self.assertTrue(fallback[2])

 def test_atomic_publish_failure_preserves_previous_file_and_cleans_temp(self):
  before = self.refresh()
  store.add_shopping(self.conn, self.hh, None, 'Bread')
  with patch.object(render.os, 'replace', side_effect=OSError('disk error')):
   fallback = self.refresh()
  self.assertEqual(before[:2], fallback[:2])
  self.assertTrue(fallback[2])
  self.assertEqual(list(self.service.directory.iterdir()), [self.service.path(self.hh)])
  self.assertNotEqual(before[0], self.refresh()[0])  # next check recovers

 def test_failed_first_render_never_returns_another_households_frame(self):
  self.refresh()
  other = store.create_household(self.conn, 'Other')
  with patch.object(render, 'png_bytes', side_effect=ValueError('bad input')):
   self.assertIsNone(self.service.refresh(self.conn, other))

 def test_invalid_render_and_corrupt_cache_are_not_served(self):
  first = self.refresh()
  with patch.object(render, 'png_bytes', return_value=b'not a PNG'):
   self.assertEqual(self.refresh()[:2], first[:2])
  self.service.path(self.hh).write_bytes(b'truncated')
  with patch.object(render, 'png_bytes', side_effect=ValueError('failed')):
   self.assertIsNone(self.refresh())

 def test_worker_rechecks_without_requests_and_stops(self):
  service = self.service
  test = self
  class Stop:
   done = False
   checks = 0
   def is_set(self): return self.done
   def wait(self, seconds):
    test.assertEqual(seconds, frames.CHECK_SECONDS)
    self.checks += 1
    if self.checks == 1:
     self.first = service.path(test.hh).read_bytes()
     store.add_shopping(test.conn, test.hh, None, 'Milk')
    else: self.done = True
  stop = Stop()
  service.run(stop)
  self.assertEqual(stop.checks, 2)
  self.assertNotEqual(stop.first, service.path(self.hh).read_bytes())


if __name__ == '__main__':
 unittest.main()
