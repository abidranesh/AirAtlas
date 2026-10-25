import { describe, expect, it } from "vitest";
import {
  correlationWord,
  festivalHeadline,
  germanyHeadlines,
  keralaHeadline,
  ratioText,
  tamilNaduHeadline,
  type FestivalEvent,
  type GermanySeasons,
  type KeralaMonsoon,
  type TamilNaduLandUse,
} from "./insights";

const event = (over: Partial<FestivalEvent> = {}): FestivalEvent => ({
  label: "new_years_eve_2022",
  kind: "new_years_eve",
  name: "New Year's Eve",
  year: 2022,
  region: "germany",
  event_day: "2022-12-31",
  anchor: "2023-01-01T00:00:00+01:00",
  series: [{ h: 0, pm25: 125, pm10: 140, n: 253 }],
  hourly: { baseline_pm25: 4, peak_pm25: 125.2, peak_hour: 0, stations: 253, ratio: 31.3 },
  daily: { event_day: null, before: null, n: 0, ratio: null },
  ...over,
});

describe("ratioText / correlationWord", () => {
  it.each([
    [31.3, "31×"],
    [2.47, "2.5×"],
    [0.58, "42% lower"],
    [null, "–"],
  ])("%s -> %s", (r, text) => expect(ratioText(r)).toBe(text));

  it.each([
    [-0.68, "strong negative"],
    [0.46, "moderate positive"],
    [-0.25, "weak negative"],
    [0.05, "no clear"],
  ])("%s -> %s", (rho, word) => expect(correlationWord(rho)).toBe(word));
});

describe("festivalHeadline", () => {
  it("describes a real rise with its baseline and station count", () => {
    expect(festivalHeadline(event())).toBe(
      "Germany, New Year's Eve 2022: the regional mean PM2.5 peaked at 125 µg/m³ at the festival hour, 31× the 4 µg/m³ typical of the days before (253 stations).",
    );
  });
  it("does not call a flat night a spike", () => {
    const flat = event({ hourly: { baseline_pm25: 19, peak_pm25: 20, peak_hour: -6, stations: 6, ratio: 1.05 } });
    expect(festivalHeadline(flat)).toContain("no clear rise");
  });
  it("falls back to daily means, and says nothing without data", () => {
    const daily = event({ series: [], hourly: { baseline_pm25: null, peak_pm25: null, peak_hour: null, stations: 0, ratio: null }, daily: { event_day: 184, before: 35.6, n: 1, ratio: 5.2 } });
    expect(festivalHeadline(daily)).toMatch(/daily mean was 184 µg\/m³ against 36 µg\/m³ .*\(1 station;/);
    expect(festivalHeadline({ ...daily, daily: { event_day: null, before: 35.6, n: 0, ratio: null } })).toBeNull();
  });
});

describe("other headlines follow the data's direction", () => {
  const kerala = (spearman: number, rainy: number, dry: number): KeralaMonsoon => ({
    monthly: [],
    by_season: {},
    rain_vs_pm25: { spearman, rainy_day_median: rainy, rainy_days: 10, dry_day_median: dry, dry_days: 10 },
    basis: { days: 20, first: null, last: null, max_stations: 1, pm: "", rain: "" },
  });
  it("Kerala: claims cleaner rainy days only when the data shows it", () => {
    expect(keralaHeadline(kerala(-0.68, 22, 43))).toContain("rainier days had cleaner air");
    expect(keralaHeadline(kerala(0.1, 30, 29))).not.toContain("cleaner");
  });

  it("Germany: no 'higher in winter' sentence when one group is lower", () => {
    const pair = (heating: number, summer: number) => ({ heating, summer, ratio: heating / summer });
    const g = (group: string, pm25: [number, number], no2: [number, number]) => ({
      group,
      stations: 10,
      pm25: pair(...pm25),
      pm10: pair(1, 1),
      no2: pair(...no2),
    });
    const d: GermanySeasons = {
      monthly: [],
      comparison: [g("urban traffic", [11.5, 7.5], [21.5, 22.7]), g("rural background", [6, 4], [6, 4.2])],
      basis: { first: null, last: null, seasons: "", stations: "" },
    };
    const [pm, no2] = germanyHeadlines(d);
    expect(pm).toContain("1.5× higher in the heating season");
    expect(no2).toContain("barely changed with the season");
    d.comparison[1].pm25 = pair(3, 4);
    expect(germanyHeadlines(d).some((h) => h.includes("heating season (October"))).toBe(false);
  });

  it("Tamil Nadu: needs both groups", () => {
    const d: TamilNaduLandUse = {
      groups: [
        { use: "industrial", stations: 4, pm25: 30, pm10: 55, so2: 32.4, no2: 16 },
        { use: "residential", stations: 1, pm25: 31, pm10: 60, so2: 15.9, no2: 14 },
      ],
      stations: [],
      diurnal: [],
      basis: {},
    };
    expect(tamilNaduHeadline(d)).toBe(
      "Median SO₂ at industrial monitors was 32 µg/m³, 2× the 16 µg/m³ at residential monitors (4 vs 1 station).",
    );
    expect(tamilNaduHeadline({ ...d, groups: d.groups.slice(0, 1) })).toBeNull();
  });
});
