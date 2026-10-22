import { describe, expect, it } from "vitest";
import { pivotMonthly } from "./compare";
import { ageText, fmt, localTime, NO_DATA_COLOR, parseScale, textOn } from "./format";
import { areaStyle, markerStyle, stationColor } from "./mapStyle";
import type { AreaSummary, Official, StationLatest } from "./types";

describe("localTime", () => {
  const iso = "2026-10-21T16:30:00Z";
  it("uses IST for India (UTC+5:30)", () => {
    expect(localTime(iso, "Asia/Kolkata")).toBe("21 Oct, 22:00 IST");
  });
  it("uses GST for the UAE (UTC+4)", () => {
    expect(localTime(iso, "Asia/Dubai", false)).toBe("20:30 GST");
  });
  it("follows German daylight saving time", () => {
    expect(localTime("2026-07-01T12:00:00Z", "Europe/Berlin", false)).toMatch(/^14:00 (CEST|GMT\+2)$/);
    expect(localTime("2026-01-15T12:00:00Z", "Europe/Berlin", false)).toMatch(/^13:00 (CET|GMT\+1)$/);
  });
});

describe("ageText", () => {
  it.each([
    [null, "no data"],
    [2, "just now"],
    [45, "45 min ago"],
    [180, "3 h ago"],
    [60 * 72, "3 d ago"],
  ])("%s min -> %s", (m, text) => expect(ageText(m)).toBe(text));
});

describe("textOn", () => {
  it("picks dark text on light AQI colours and light text on dark ones", () => {
    expect(textOn("#FFFF00")).toBe("#000000"); // CPCB 'moderately polluted' yellow
    expect(textOn("#50F0E6")).toBe("#000000"); // EEA 'good'
    expect(textOn("#7E0023")).toBe("#ffffff"); // UAE 'hazardous' maroon
    expect(textOn("#960032")).toBe("#ffffff"); // EEA 'very poor'
  });
});

describe("parseScale", () => {
  it("defaults to local where allowed, else the European AQI", () => {
    expect(parseScale(null, true)).toBe("local");
    expect(parseScale(null, false)).toBe("eu_eaqi");
    expect(parseScale("who_2021_pm25", false)).toBe("who_2021_pm25");
    expect(parseScale("us_aqi", true)).toBe("local");
  });
});

describe("fmt", () => {
  it("renders missing numbers as a dash, never as 0", () => {
    expect(fmt(null)).toBe("–");
    expect(fmt(undefined)).toBe("–");
    expect(fmt(Number.NaN)).toBe("–");
    expect(fmt(0)).toBe("0");
  });
});

const cat = (color: string, level = 2) => ({ key: "k", label: "L", color, level });
function station(over: Partial<StationLatest>): StationLatest {
  return {
    id: 1, name: "S", city: null, area_id: 1, area: "A", kind: "reference", setting: null, station_type: null,
    lat: 0, lon: 0, region: "kerala", latest_ts: null, age_minutes: null, freshness: "fresh",
    aqi: null, concentrations: null, official: null, ...over,
  };
}

describe("map styles", () => {
  it("colours by computed AQI, then by CPCB's official index, then grey", () => {
    const official: Official = { source: "cpcb", standard: "in_cpcb_naqi", value: 54, category: cat("#92D050"), dominant: [], reported_at: "", sub_indices: {}, note: "" };
    expect(stationColor(station({ aqi: { standard: "x", status: "ok", value: 3, level: 3, category: cat("#F0E641", 3), dominant: [] } }))).toBe("#F0E641");
    expect(stationColor(station({ official }))).toBe("#92D050");
    expect(stationColor(station({}))).toBe(NO_DATA_COLOR);
  });

  it("draws modeled points as hollow rings and dims monitors without data", () => {
    expect(markerStyle(station({ kind: "modeled" })).fillOpacity).toBe(0);
    expect(markerStyle(station({ kind: "low_cost" })).dashArray).toBeDefined();
    expect(markerStyle(station({})).fillOpacity).toBeLessThan(0.95);
  });

  it("marks modeled areas with a dashed outline and lighter fill", () => {
    const measured: AreaSummary = { area_id: 1, name: "A", value: 80, basis: "measured", n_stations: 2, category: cat("#FFFF00") };
    const modeled: AreaSummary = { ...measured, basis: "modeled" };
    expect(areaStyle(measured).dashArray).toBeUndefined();
    expect(areaStyle(modeled).dashArray).toBe("4 4");
    expect(areaStyle(modeled).fillOpacity!).toBeLessThan(areaStyle(measured).fillOpacity!);
    expect(areaStyle(undefined).fillColor).toBe(NO_DATA_COLOR);
  });
});

describe("pivotMonthly", () => {
  it("makes one sorted row per month with a column per region and leaves gaps empty", () => {
    const rows = pivotMonthly([
      { region: "germany", area: "Berlin", month: "2026-09-01", pm25: 8.1, stations: 3, station_days: 90 },
      { region: "uae", area: "Dubai", month: "2026-08-01", pm25: 41.2, stations: 2, station_days: 50 },
      { region: "germany", area: "Berlin", month: "2026-08-01", pm25: 7.4, stations: 3, station_days: 93 },
    ]);
    expect(rows).toEqual([
      { month: "2026-08-01", uae: 41.2, germany: 7.4 },
      { month: "2026-09-01", germany: 8.1 },
    ]);
  });
});
