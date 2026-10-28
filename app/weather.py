"""Server-side weather adapter with a cache. Displays never call weather providers.

Only FakeProvider exists. A real provider makes external network calls, so it needs separate approval first.
"""
import json
from . import solar, store

MAX_AGE = 30*60  # refetch after 30 minutes (plan: 15–30)

class FakeProvider:
 """Returns fixed demo values. Used for the demo and in tests."""
 def __init__(self, sample):
  self.sample = {'temperature': sample.get('temperature'), 'condition': sample.get('condition')}

 def fetch(self, lat, lon):
  return dict(self.sample)

def current(conn, household_id, provider, now, max_age=MAX_AGE):
 """Cached weather with its age in minutes. Keeps the last good value when a refresh fails."""
 row = store.get_weather(conn, household_id)
 location = store.get_location(conn, household_id)
 if row is None or now - row['fetched_at'] >= max_age:
  try:
   payload = provider.fetch(location['lat'] if location else None, location['lon'] if location else None)
   store.put_weather(conn, household_id, now, json.dumps(payload))
   row = store.get_weather(conn, household_id)
  except (OSError, ValueError):
   pass  # keep the last-known-good value; the age tells the display it is stale
 if row is None: return None
 return {**json.loads(row['payload']), 'age_minutes': max(0, (now - row['fetched_at']) // 60)}

def frame_weather(conn, household_id, provider, now, today):
 """The weather block the renderer receives. Missing values are left out so the renderer shows its own placeholders."""
 block = {}
 weather = current(conn, household_id, provider, now)
 if weather:
  block.update(temperature=weather.get('temperature'), condition=weather.get('condition'), age_minutes=weather['age_minutes'])
 location = store.get_location(conn, household_id)
 if location:
  sunset = solar.sunset_local(today, location['lat'], location['lon'], location['tz'])
  if sunset: block['sunset'] = sunset
 return {k: v for k, v in block.items() if v is not None}
