import { OpenMeteoResponse } from "@/types/api";

const WMO_CODES: Record<number, string> = {
  0: "Clear",
  1: "Partly cloudy",
  2: "Partly cloudy",
  3: "Partly cloudy",
  45: "Fog",
  48: "Fog",
  51: "Drizzle",
  53: "Drizzle",
  55: "Drizzle",
  61: "Rain",
  63: "Rain",
  65: "Rain",
  71: "Snow",
  73: "Snow",
  75: "Snow",
  80: "Showers",
  81: "Showers",
  82: "Showers",
  95: "Thunderstorm",
};

function mapWeatherCode(code: number): string {
  return WMO_CODES[code] ?? "Unknown";
}

function celsiusToFahrenheit(c: number): number {
  return Math.round((c * 9) / 5 + 32);
}

function kmhToMph(kmh: number): number {
  return Math.round(kmh * 0.621371);
}

export default async function WeatherWidget() {
  const lat = process.env.WEATHER_LAT;
  const lon = process.env.WEATHER_LON;

  if (!lat || !lon) {
    return (
      <div className="bg-white rounded-2xl shadow-md p-6 text-center">
        <p className="text-gray-500 text-sm">Weather unavailable</p>
      </div>
    );
  }

  let data: OpenMeteoResponse | null = null;

  try {
    const res = await fetch(
      `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current_weather=true`,
      { next: { revalidate: 1800 } },
    );
    if (res.ok) {
      data = (await res.json()) as OpenMeteoResponse;
    }
  } catch {
    // fall through to error state below
  }

  if (!data) {
    return (
      <div className="bg-white rounded-2xl shadow-md p-6 text-center">
        <p className="text-gray-500 text-sm">Weather unavailable</p>
      </div>
    );
  }

  const { temperature, windspeed, weathercode } = data.current_weather;
  const tempF = celsiusToFahrenheit(temperature);
  const windMph = kmhToMph(windspeed);
  const condition = mapWeatherCode(weathercode);

  return (
    <div className="bg-white rounded-2xl shadow-md p-6 text-center">
      <p className="text-gray-500 text-sm mb-1">Current Conditions</p>
      <p className="text-gray-800 text-2xl font-semibold">{tempF}°F</p>
      <p className="text-gray-800 text-base">{condition}</p>
      <p className="text-gray-500 text-sm">Wind {windMph} mph</p>
    </div>
  );
}
