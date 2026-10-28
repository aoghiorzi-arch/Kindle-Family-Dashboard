"""Input checks shared by the web API and the command line."""
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .auth import valid_username, MIN_PASSWORD

TIME = re.compile(r'^([01]?\d|2[0-3]):[0-5]\d$')
ROLES = ('member', 'admin')

def clean_title(value, limit=100):
 if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
  raise ValueError(f'Title must be 1–{limit} characters')
 return value.strip()

def clean_time(value):
 if not isinstance(value, str) or len(value) > 30:
  raise ValueError('Invalid time')
 value = value.strip()
 if value and not TIME.match(value):
  raise ValueError('Time must look like 17:30 or be left blank')
 return value

def clean_username(value):
 if not isinstance(value, str) or not valid_username(value):
  raise ValueError('Usernames are 2–32 characters: letters, digits, _ . or -')
 return value

def clean_password(value):
 if not isinstance(value, str) or len(value) < MIN_PASSWORD:
  raise ValueError(f'Password must be at least {MIN_PASSWORD} characters')
 return value

def clean_role(value):
 if value not in ROLES:
  raise ValueError('Role must be member or admin')
 return value

def clean_location(lat, lon, tz):
 try:
  lat, lon = float(lat), float(lon)
 except (TypeError, ValueError):
  raise ValueError('Latitude and longitude must be numbers')
 if not (-90 <= lat <= 90 and -180 <= lon <= 180):
  raise ValueError('Latitude must be -90 to 90 and longitude -180 to 180')
 if not isinstance(tz, str):
  raise ValueError('Unknown time zone')
 try:
  ZoneInfo(tz)
 except (ZoneInfoNotFoundError, ValueError):
  raise ValueError(f'Unknown time zone: {tz}')
 return lat, lon, tz
