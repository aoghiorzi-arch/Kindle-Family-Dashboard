import unittest, tempfile, json
from datetime import date
from pathlib import Path
from unittest.mock import patch
from PIL import ImageDraw
from app import solar, store, weather, auth
from app.render import render

FIXTURE = json.loads((Path(__file__).resolve().parents[1]/'app'/'seed.json').read_text())

class CountingProvider:
 def __init__(self, sample):
  self.sample, self.calls, self.fail = sample, 0, False

 def fetch(self, lat, lon):
  self.calls += 1
  if self.fail: raise OSError('provider down')
  return dict(self.sample)

class SolarTest(unittest.TestCase):
 def test_london_summer_and_autumn_sunset(self):
  self.assertEqual(solar.sunset_local('2026-06-21', 51.5074, -0.1278, 'Europe/London'), '21:21')
  self.assertEqual(solar.sunset_local('2026-10-28', 51.5074, -0.1278, 'Europe/London'), '16:42')

 def test_equinox_at_greenwich_is_close_to_18_utc(self):
  utc = solar.sunset_utc(date(2026, 3, 20), 0, 0)
  self.assertLess(abs(utc.hour*60 + utc.minute - (18*60 + 10)), 3)

 def test_no_sunset_inside_polar_day(self):
  self.assertIsNone(solar.sunset_local('2026-06-21', 78.2, 15.6, 'Europe/Oslo'))

class WeatherCacheTest(unittest.TestCase):
 def setUp(self):
  self.tmp = tempfile.TemporaryDirectory()
  self.db = Path(self.tmp.name)/'f.sqlite3'
  store.init_db(self.db)
  self.conn = store.connect(self.db)
  self.hh = store.create_household(self.conn, 'Test')
  self.provider = CountingProvider({'temperature': 9, 'condition': 'Rain'})

 def tearDown(self):
  self.conn.close()
  self.tmp.cleanup()

 def test_fetches_once_then_serves_cache_until_max_age(self):
  first = weather.current(self.conn, self.hh, self.provider, now=1000)
  again = weather.current(self.conn, self.hh, self.provider, now=1000 + 600)
  self.assertEqual(self.provider.calls, 1)
  self.assertEqual((first['temperature'], again['age_minutes']), (9, 10))

 def test_refetches_after_max_age(self):
  weather.current(self.conn, self.hh, self.provider, now=0)
  weather.current(self.conn, self.hh, self.provider, now=weather.MAX_AGE)
  self.assertEqual(self.provider.calls, 2)

 def test_failed_refresh_keeps_last_good_value_with_age(self):
  weather.current(self.conn, self.hh, self.provider, now=0)
  self.provider.fail = True
  stale = weather.current(self.conn, self.hh, self.provider, now=3*3600)
  self.assertEqual(stale['condition'], 'Rain')
  self.assertEqual(stale['age_minutes'], 180)

 def test_no_cache_and_failing_provider_gives_nothing(self):
  self.provider.fail = True
  self.assertIsNone(weather.current(self.conn, self.hh, self.provider, now=0))
  self.assertEqual(weather.frame_weather(self.conn, self.hh, self.provider, 0, '2026-10-28'), {})

 def test_sunset_from_location_when_set(self):
  store.set_location(self.conn, self.hh, 51.5074, -0.1278, 'Europe/London')
  block = weather.frame_weather(self.conn, self.hh, self.provider, 0, '2026-10-28')
  self.assertEqual(block['sunset'], '16:42')
  self.assertEqual(block['temperature'], 9)

 def test_fixture_sunset_is_not_used_when_no_weather_available(self):
  self.provider.fail = True
  self.assertNotIn('sunset', weather.frame_weather(self.conn, self.hh, self.provider, 0, '2026-10-28'))

class StaleRenderTest(unittest.TestCase):
 def drawn(self, weather_block):
  drawn = []
  original = ImageDraw.ImageDraw.text
  def capture(self, xy, text, *args, **kwargs):
   drawn.append(str(text)); return original(self, xy, text, *args, **kwargs)
  data = json.loads(json.dumps(FIXTURE)); data['weather'] = weather_block
  with patch.object(ImageDraw.ImageDraw, 'text', capture):
   render(data)
  return drawn

 def test_old_forecast_shows_its_age(self):
  self.assertIn('Updated 3 h ago', self.drawn({'temperature': 14, 'condition': 'Rain', 'age_minutes': 190}))

 def test_fresh_forecast_shows_no_age(self):
  self.assertFalse(any(t.startswith('Updated') for t in self.drawn({'temperature': 14, 'condition': 'Rain', 'age_minutes': 5})))

if __name__ == '__main__':
 unittest.main()
