"""Sunset from latitude, longitude and date (NOAA-style approximation, roughly ±1 minute at mid-latitudes)."""
import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

J2000 = 2451545.0
UNIX_EPOCH_JD = 2440587.5

def sunset_utc(day, lat, lon):
 """Sunset as an aware UTC datetime, or None when the sun does not set that day (polar)."""
 jd_noon = (day - date(1970, 1, 1)).days + UNIX_EPOCH_JD + 0.5
 n = round(jd_noon - J2000 + 0.0008)
 j_star = n - lon / 360  # longitude is east-positive
 m = math.radians((357.5291 + 0.98560028 * j_star) % 360)
 centre = 1.9148 * math.sin(m) + 0.02 * math.sin(2 * m) + 0.0003 * math.sin(3 * m)
 ecliptic = math.radians((math.degrees(m) + centre + 180 + 102.9372) % 360)
 j_transit = J2000 + j_star + 0.0053 * math.sin(m) - 0.0069 * math.sin(2 * ecliptic)
 sin_dec = math.sin(ecliptic) * math.sin(math.radians(23.4397))
 cos_dec = math.cos(math.asin(sin_dec))
 phi = math.radians(lat)
 cos_w = (math.sin(math.radians(-0.833)) - math.sin(phi) * sin_dec) / (math.cos(phi) * cos_dec)
 if not -1 <= cos_w <= 1: return None
 hour_angle = math.degrees(math.acos(cos_w))
 j_set = j_transit + hour_angle / 360
 return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(days=j_set - UNIX_EPOCH_JD)

def sunset_local(day_iso, lat, lon, tz):
 """'HH:MM' in the household's time zone, or None when there is no sunset."""
 utc = sunset_utc(date.fromisoformat(day_iso), lat, lon)
 return None if utc is None else utc.astimezone(ZoneInfo(tz)).strftime('%H:%M')
