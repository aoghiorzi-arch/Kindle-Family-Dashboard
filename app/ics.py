"""Read-only iCalendar (.ics) import. Parses text the family pastes in; it never fetches URLs.

Supported: single events with DTSTART as a date (all-day) or date-time (UTC, TZID or floating).
Not supported: recurring events (RRULE or RECURRENCE-ID). They are counted as skipped, not expanded.
"""
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re

MAX_EVENTS = 500
DATE_TIME = re.compile(r'(\d{8})T(\d{6})(Z?)')

def unfold(text):
 """RFC 5545 line unfolding: a line starting with a space or tab continues the previous line."""
 lines = []
 for raw in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
  if raw[:1] in (' ', '\t') and lines:
   lines[-1] += raw[1:]
  else:
   lines.append(raw)
 return lines

def unescape(value):
 return re.sub(r'\\(.)', lambda m: ' ' if m.group(1) in 'nN' else m.group(1), value)

def parse_property(line):
 head, _, value = line.partition(':')
 parts = head.split(';')
 params = {}
 for part in parts[1:]:
  key, _, val = part.partition('=')
  params[key.upper()] = val.strip('"')
 return parts[0].upper(), params, value

def to_local(value, params, household_tz):
 """(day, 'HH:MM') in the household's time zone; the time is '' for all-day events."""
 if params.get('VALUE') == 'DATE' or re.fullmatch(r'\d{8}', value):
  return datetime.strptime(value, '%Y%m%d').date().isoformat(), ''
 match = DATE_TIME.fullmatch(value)
 if not match:
  raise ValueError(f'Unreadable date: {value}')
 naive = datetime.strptime(match.group(1) + match.group(2), '%Y%m%d%H%M%S')
 if match.group(3) == 'Z':
  source = ZoneInfo('UTC')
 else:
  try:
   source = ZoneInfo(params['TZID']) if 'TZID' in params else ZoneInfo(household_tz)
  except (ZoneInfoNotFoundError, ValueError):
   source = ZoneInfo(household_tz)
 local = naive.replace(tzinfo=source).astimezone(ZoneInfo(household_tz))
 return local.date().isoformat(), local.strftime('%H:%M')

def build_event(props, household_tz):
 if props.get('status') == 'CANCELLED' or props.get('recurring') or 'start' not in props:
  return None
 try:
  day, when = to_local(props['start'][0], props['start'][1], household_tz)
 except (ValueError, OverflowError):
  return None
 title = ' '.join(unescape(props.get('title', '')).split())[:100] or 'Untitled'
 return {'uid': props.get('uid', ''), 'day': day, 'time': when, 'title': title, 'private': bool(props.get('private'))}

def parse_events(text, household_tz):
 """Returns (events, skipped). Raises ValueError when there are more events than MAX_EVENTS."""
 events, skipped, props = [], 0, None
 for line in unfold(text):
  if line == 'BEGIN:VEVENT':
   props = {}
   continue
  if props is None or not line.strip():
   continue
  if line == 'END:VEVENT':
   event = build_event(props, household_tz)
   if event is None:
    skipped += 1
   else:
    events.append(event)
    if len(events) > MAX_EVENTS: raise ValueError(f'Too many events (limit {MAX_EVENTS})')
   props = None
   continue
  name, params, value = parse_property(line)
  if name in ('RRULE', 'RECURRENCE-ID'): props['recurring'] = True
  elif name == 'STATUS': props['status'] = value.strip().upper()
  elif name == 'SUMMARY': props['title'] = value
  elif name == 'UID': props['uid'] = value.strip()
  elif name == 'CLASS': props['private'] = value.strip().upper() in ('PRIVATE', 'CONFIDENTIAL')
  elif name == 'DTSTART': props['start'] = (value.strip(), params)
 return events, skipped
