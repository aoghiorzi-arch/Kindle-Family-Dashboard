"""Offline iCalendar import, with bounded recurrence expansion in an isolated worker."""
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import subprocess
import sys

MAX_EVENTS = 500
MAX_BYTES = 2_000_000
WINDOW_DAYS = 31
PARSE_SECONDS = 6


def parse_events(text, household_tz, today=None):
 """Return (events, skipped). Singles retain their dates; series cover a rolling 31 days.

 The worker has a wall-clock deadline and, on Unix, a memory/CPU ceiling. Invalid
 or oversized sources raise a fixed ValueError so callers keep their last good data.
 """
 if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_BYTES:
  raise ValueError('Calendar is too large')
 today = today or datetime.now(ZoneInfo(household_tz)).date().isoformat()
 try:
  result = subprocess.run([sys.executable, '-m', 'app.ics', '--worker'],
   input=json.dumps({'text': text, 'tz': household_tz, 'today': today}),
   capture_output=True, text=True, timeout=PARSE_SECONDS,
   cwd=Path(__file__).resolve().parents[1])
  if result.returncode: raise ValueError('Calendar could not be read within the supported limits')
  events, skipped = json.loads(result.stdout)
  return events, skipped
 except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
  raise ValueError('Calendar could not be read within the supported limits') from None


def _parse(text, household_tz, today):
 from icalendar import Calendar
 import recurring_ical_events
 tz = ZoneInfo(household_tz)
 cal = Calendar.from_ical(text)
 if cal.name != 'VCALENDAR': raise ValueError('Not a calendar')
 components = cal.walk('VEVENT')
 if len(components) > MAX_EVENTS: raise ValueError('Too many events')
 recurring = {str(c.get('UID', '')) for c in components if any(k in c for k in ('RRULE', 'RDATE', 'RECURRENCE-ID'))}
 groups, singles, skipped = {}, [], 0
 for component in components:
  if component.errors:
   skipped += 1
   continue
  # Floating and unknown-TZID times use the household zone, including exceptions.
  for name in ('DTSTART', 'DTEND', 'RECURRENCE-ID', 'EXDATE', 'RDATE'):
   properties = component.get(name, [])
   if not isinstance(properties, list): properties = [properties]
   for prop in properties:
    for part in getattr(prop, 'dts', [prop]):
     dt = getattr(part, 'dt', None)
     if isinstance(dt, datetime) and dt.tzinfo is None:
      part.dt = dt.replace(tzinfo=tz)
  uid = str(component.get('UID', ''))
  if uid in recurring:
   groups.setdefault(uid, []).append(component)
  else:
   event = _event(component, tz)
   if event is None: skipped += 1
   else: singles.append(event)
 start = datetime.combine(date.fromisoformat(today), time.min, tzinfo=tz)
 end = start + timedelta(days=WINDOW_DAYS)
 events = list(singles)
 for uid, group in groups.items():
  masters = [c for c in group if 'RECURRENCE-ID' not in c]
  if not uid or not masters or any('DTSTART' not in c for c in masters):
   skipped += len(group)
   continue
  # Subdaily repetition is not useful on this display and can expand explosively.
  if any(str(c.get('RRULE', {}).get('FREQ', ['DAILY'])[0]) not in ('DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY')
         for c in masters):
   skipped += len(group)
   continue
  subset = Calendar()
  subset.add('VERSION', '2.0')
  for c in group: subset.add_component(c)
  master_private = any(str(c.get('CLASS', '')).upper() in ('PRIVATE', 'CONFIDENTIAL') for c in masters)
  try:
   occurrences = recurring_ical_events.of(subset).between(start, end)
  except Exception:
   skipped += len(group)
   continue
  for occurrence in occurrences:
   event = _event(occurrence, tz)
   if event is not None and start.date().isoformat() <= event['day'] < end.date().isoformat():
    event['private'] = event['private'] or master_private
    events.append(event)
    if len(events) > MAX_EVENTS: raise ValueError('Too many occurrences')
 return sorted(events, key=lambda event: (event['day'], event['time'], event['uid'])), skipped


def _event(component, tz):
 if str(component.get('STATUS', '')).upper() == 'CANCELLED': return None
 try:
  dt = component.decoded('DTSTART')
  if isinstance(dt, datetime):
   dt = (dt if dt.tzinfo else dt.replace(tzinfo=tz)).astimezone(tz)
   day, when = dt.date().isoformat(), dt.strftime('%H:%M')
  elif isinstance(dt, date): day, when = dt.isoformat(), ''
  else: return None
 except (ValueError, KeyError, TypeError, OverflowError): return None
 return {'uid': str(component.get('UID', '')), 'day': day, 'time': when,
  'title': ' '.join(str(component.get('SUMMARY', '')).split())[:100] or 'Untitled',
  'private': str(component.get('CLASS', '')).upper() in ('PRIVATE', 'CONFIDENTIAL')}


if __name__ == '__main__' and sys.argv[1:] == ['--worker']:
 try:
  try:
   import resource
   resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
   resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
  except ImportError: pass
  payload = json.load(sys.stdin)
  print(json.dumps(_parse(payload['text'], payload['tz'], payload['today'])))
 except Exception:
  sys.exit(1)
