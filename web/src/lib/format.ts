import type { CommonScale, RegionCode, Scale, StationKind } from "./types";

export const REGION_NAMES: Record<RegionCode, string> = {
  tamil_nadu: "Tamil Nadu",
  kerala: "Kerala",
  uae: "United Arab Emirates",
  germany: "Germany",
};

export const SCALE_LABELS: Record<Scale, string> = {
  local: "Local standard",
  eu_eaqi: "European AQI",
  who_2021_pm25: "WHO PM2.5",
};

export function parseScale(value: string | null | undefined, allowLocal: true): Scale;
export function parseScale(value: string | null | undefined, allowLocal: false): CommonScale;
export function parseScale(value: string | null | undefined, allowLocal: boolean): Scale {
  if (value === "eu_eaqi" || value === "who_2021_pm25") return value;
  return allowLocal ? "local" : "eu_eaqi";
}

export const POLLUTANTS: Record<string, { label: string; unit: string }> = {
  pm25: { label: "PM2.5", unit: "µg/m³" },
  pm10: { label: "PM10", unit: "µg/m³" },
  no2: { label: "NO₂", unit: "µg/m³" },
  o3: { label: "O₃", unit: "µg/m³" },
  so2: { label: "SO₂", unit: "µg/m³" },
  co: { label: "CO", unit: "mg/m³" },
  nh3: { label: "NH₃", unit: "µg/m³" },
  dust: { label: "Dust", unit: "µg/m³" },
};

export const KIND_LABELS: Record<StationKind, string> = {
  reference: "Measured",
  low_cost: "Low-cost sensor",
  modeled: "Modeled",
};

// Intl's short names for these zones are often "GMT+5:30"; people know them as IST / GST.
const TZ_ABBREV: Record<string, string> = { "Asia/Kolkata": "IST", "Asia/Dubai": "GST" };

export function localTime(iso: string, timeZone: string, withDate = true): string {
  const d = new Date(iso);
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    ...(withDate ? { day: "numeric", month: "short" } : {}),
    ...(TZ_ABBREV[timeZone] ? {} : { timeZoneName: "short" }),
  }).format(d);
  return TZ_ABBREV[timeZone] ? `${parts} ${TZ_ABBREV[timeZone]}` : parts;
}

export function ageText(minutes: number | null): string {
  if (minutes === null) return "no data";
  if (minutes < 5) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 48 * 60) return `${Math.floor(minutes / 60)} h ago`;
  return `${Math.floor(minutes / 1440)} d ago`;
}

/** Black or white text, whichever has the higher WCAG contrast on `hex`. */
export function textOn(hex: string): "#000000" | "#ffffff" {
  const h = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(h.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  const L = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return (L + 0.05) / 0.05 >= 1.05 / (L + 0.05) ? "#000000" : "#ffffff";
}

export function fmt(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  return value.toLocaleString("en-GB", { maximumFractionDigits: digits });
}

export const NO_DATA_COLOR = "#a3a3a3";
