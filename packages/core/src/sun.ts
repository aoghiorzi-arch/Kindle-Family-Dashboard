// Sunrise and sunset from latitude, longitude and date. NOAA-style approximation, about one minute at mid-latitudes.
// Ported from app/solar.py. The sunset path matches the Python implementation (see test/sun.test.ts).

const J2000 = 2451545.0;
const UNIX_EPOCH_JD = 2440587.5;
const DAY_MS = 86_400_000;

const mod360 = (x: number) => ((x % 360) + 360) % 360;
const rad = (deg: number) => (deg * Math.PI) / 180;
const deg = (r: number) => (r * 180) / Math.PI;

// Returns the event instant as a Date, or null when the sun neither rises nor sets that day.
function sunEvent(day: string, lat: number, lon: number, sunrise: boolean): Date | null {
  const [y, m, d] = day.split("-").map(Number);
  const daysSinceEpoch = Date.UTC(y, m - 1, d) / DAY_MS;
  const jdNoon = daysSinceEpoch + UNIX_EPOCH_JD + 0.5;
  const n = Math.round(jdNoon - J2000 + 0.0008);
  const jStar = n - lon / 360; // longitude is east-positive
  const M = rad(mod360(357.5291 + 0.9856002 * jStar));
  const centre = 1.9148 * Math.sin(M) + 0.02 * Math.sin(2 * M) + 0.0003 * Math.sin(3 * M);
  const ecliptic = rad(mod360(deg(M) + centre + 180 + 102.9372));
  const jTransit = J2000 + jStar + 0.0053 * Math.sin(M) - 0.0069 * Math.sin(2 * ecliptic);
  const sinDec = Math.sin(ecliptic) * Math.sin(rad(23.4397));
  const cosDec = Math.cos(Math.asin(sinDec));
  const phi = rad(lat);
  const cosW = (Math.sin(rad(-0.833)) - Math.sin(phi) * sinDec) / (Math.cos(phi) * cosDec);
  if (cosW < -1 || cosW > 1) return null;
  const hourAngle = deg(Math.acos(cosW));
  const jEvent = sunrise ? jTransit - hourAngle / 360 : jTransit + hourAngle / 360;
  return new Date(Math.round((jEvent - UNIX_EPOCH_JD) * DAY_MS));
}

export function sunsetUtc(day: string, lat: number, lon: number): Date | null {
  return sunEvent(day, lat, lon, false);
}

export function sunriseUtc(day: string, lat: number, lon: number): Date | null {
  return sunEvent(day, lat, lon, true);
}

// "HH:MM" in the given zone, or null.
export function clockTime(instant: Date | null, timezone: string): string | null {
  if (!instant) return null;
  return new Intl.DateTimeFormat("en-GB", { timeZone: timezone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(instant);
}
