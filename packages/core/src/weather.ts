// Weather from Open-Meteo (CC BY 4.0). The free API is for non-commercial use: confirm before deployment (docs/PHASE5_INTEGRATIONS.md).
// Response shape assumed from Open-Meteo's documented `current` block; not yet checked against a live response.

export const WEATHER_ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)";

export interface WeatherReading {
  temperatureC: number;
  summary: string;
  observedAt: string; // UTC, as Open-Meteo returns it in the requested timezone; stored as received
}

// WMO weather interpretation codes, as summarised in Open-Meteo's documentation.
const WMO: Record<number, string> = {
  0: "Clear sky",
  1: "Mainly clear",
  2: "Partly cloudy",
  3: "Overcast",
  45: "Fog",
  48: "Fog",
  51: "Drizzle",
  53: "Drizzle",
  55: "Drizzle",
  56: "Freezing drizzle",
  57: "Freezing drizzle",
  61: "Rain",
  63: "Rain",
  65: "Heavy rain",
  66: "Freezing rain",
  67: "Freezing rain",
  71: "Snow",
  73: "Snow",
  75: "Heavy snow",
  77: "Snow grains",
  80: "Rain showers",
  81: "Rain showers",
  82: "Heavy rain showers",
  85: "Snow showers",
  86: "Heavy snow showers",
  95: "Thunderstorm",
  96: "Thunderstorm, hail",
  99: "Thunderstorm, hail",
};

export function summaryForCode(code: number): string {
  return WMO[code] ?? "Weather";
}

export function parseOpenMeteoCurrent(body: unknown): WeatherReading {
  const current = (body as { current?: Record<string, unknown> } | null)?.current;
  const temperature = current?.temperature_2m;
  const code = current?.weather_code;
  const time = current?.time;
  if (typeof temperature !== "number" || !Number.isFinite(temperature) || temperature < -60 || temperature > 60) {
    throw new Error("weather: temperature missing or out of range");
  }
  if (typeof code !== "number" || !Number.isInteger(code) || code < 0 || code > 99) {
    throw new Error("weather: weather code missing or out of range");
  }
  if (typeof time !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(time)) {
    throw new Error("weather: observation time missing");
  }
  return { temperatureC: Math.round(temperature), summary: summaryForCode(code), observedAt: time };
}

// Open-Meteo request for one location. Only the current block is needed.
export function openMeteoUrl(latitude: number, longitude: number, timezone: string): string {
  const params = new URLSearchParams({
    latitude: latitude.toFixed(4),
    longitude: longitude.toFixed(4),
    current: "temperature_2m,weather_code",
    timezone,
  });
  return `https://api.open-meteo.com/v1/forecast?${params.toString()}`;
}
