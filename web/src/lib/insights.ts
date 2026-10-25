import { fmt, REGION_NAMES } from "./format";
import type { RegionCode } from "./types";

// Shapes of /api/v1/insights/{slug}. Every number on the insight pages comes from these responses;
// the sentences below are templates filled from them and return null when the data isn't there.

export interface FestivalEvent {
  label: string;
  kind: "deepavali" | "bhogi" | "new_years_eve";
  name: string;
  year: number;
  region: RegionCode;
  event_day: string;
  anchor: string;
  series: { h: number; pm25: number | null; pm10: number | null; n: number }[];
  hourly: { baseline_pm25: number | null; peak_pm25: number | null; peak_hour: number | null; stations: number; ratio: number | null };
  daily: { event_day: number | null; before: number | null; n: number; ratio: number | null };
}
export interface Festivals {
  events: FestivalEvent[];
  method: Record<"alignment" | "baseline" | "peak" | "daily", string>;
}

export type KeralaSeason = "Winter" | "Pre-monsoon" | "Southwest monsoon" | "Northeast monsoon";
export interface KeralaMonsoon {
  monthly: { month: string; season: KeralaSeason; pm25: number | null; pm10: number | null; rain_mm: number | null; days: number }[];
  by_season: Partial<Record<KeralaSeason, { pm25_median: number | null; rain_mm_per_day: number | null; days: number }>>;
  rain_vs_pm25: { spearman: number | null; rainy_day_median: number | null; rainy_days: number; dry_day_median: number | null; dry_days: number };
  basis: { days: number; first: string | null; last: string | null; max_stations: number; pm: string; rain: string };
}

export interface UaeDust {
  daily: { day: string; pm25: number | null; n: number; dust: number | null; dust_peak: number | null; model_pm10: number | null; wind: number | null }[];
  dust_vs_pm25: {
    spearman: number | null;
    dusty_day_median: number | null;
    dusty_days: number;
    clear_day_median: number | null;
    clear_days: number;
    wind_vs_dust: number | null;
    thresholds: { dusty_q3: number | null; clear_q1: number | null };
  };
  spikes: { total: number; with_dust_hint: number; top: { station: string; peak_at: string; peak: number; baseline: number | null; dust_max: number | null }[] };
  basis: { days: number; paired_days: number; measured: string; modeled: string; first: string | null; last: string | null };
}

export type GermanPollutant = "pm25" | "pm10" | "no2";
export interface SeasonPair {
  heating: number | null;
  summer: number | null;
  ratio: number | null;
}
export interface GermanySeasons {
  monthly: ({ group: string; month: string; stations: number } & Record<GermanPollutant, number | null>)[];
  comparison: ({ group: string; stations: number } & Record<GermanPollutant, SeasonPair>)[];
  basis: { first: string | null; last: string | null; seasons: string; stations: string };
}

export type LandUse = "industrial" | "residential";
export type TnPollutant = "pm25" | "pm10" | "so2" | "no2";
export interface TamilNaduLandUse {
  groups: ({ use: LandUse; stations: number } & Record<TnPollutant, number | null>)[];
  stations: ({ id: number; name: string; use: LandUse; basis: string; days: number; first: string; last: string } & Record<TnPollutant, number | null>)[];
  diurnal: { use: LandUse; hour: number; so2: number | null; pm25: number | null; no2: number | null }[];
  basis: { period?: string; rules?: { use: LandUse; matches: string; basis: string }[]; unclassified?: number; note?: string };
}

export const INSIGHTS = [
  {
    slug: "festivals",
    title: "Festival nights",
    region: "Tamil Nadu, Kerala, UAE, Germany",
    blurb: "Deepavali, Bhogi and New Year's Eve, hour by hour against the days before.",
  },
  {
    slug: "kerala-monsoon",
    title: "Kerala's monsoon washout",
    region: "Kerala",
    blurb: "How rain through the southwest and northeast monsoons relates to particulate levels.",
  },
  {
    slug: "uae-dust",
    title: "UAE dust days",
    region: "United Arab Emirates",
    blurb: "Modeled desert dust next to measured PM2.5, day by day, and the spikes that came with dust.",
  },
  {
    slug: "germany-seasons",
    title: "Germany: heating season, city vs countryside",
    region: "Germany",
    blurb: "Winter versus summer, and traffic sites versus rural background stations.",
  },
  {
    slug: "tamil-nadu-land-use",
    title: "Tamil Nadu: industrial vs residential",
    region: "Tamil Nadu",
    blurb: "Monitors in industrial estates compared with residential monitors.",
  },
] as const;
export type InsightSlug = (typeof INSIGHTS)[number]["slug"];
export const isInsight = (s: string): s is InsightSlug => INSIGHTS.some((i) => i.slug === s);

/** "×3.2" style ratios; below 1 reads better as a percentage drop. */
export function ratioText(ratio: number | null | undefined): string {
  if (ratio == null) return "–";
  if (ratio >= 1) return `${fmt(ratio, ratio >= 10 ? 0 : 1)}×`;
  return `${fmt((1 - ratio) * 100, 0)}% lower`;
}

/** Plain-language strength for a Spearman coefficient. */
export function correlationWord(rho: number): string {
  const a = Math.abs(rho);
  const strength = a >= 0.6 ? "strong" : a >= 0.4 ? "moderate" : a >= 0.2 ? "weak" : "no clear";
  if (strength === "no clear") return "no clear";
  return `${strength} ${rho < 0 ? "negative" : "positive"}`;
}

export function hourOffsetText(h: number): string {
  if (h === 0) return "at the festival hour";
  return `${Math.abs(h)} h ${h < 0 ? "before" : "after"}`;
}

export const hasFestivalData = (e: FestivalEvent) => e.series.length > 0 || e.daily.n > 0;

export function festivalHeadline(e: FestivalEvent): string | null {
  const h = e.hourly;
  if (h.peak_pm25 != null && h.baseline_pm25 != null && h.peak_hour != null) {
    const rise = h.ratio != null && h.ratio >= 1.2;
    return (
      `${REGION_NAMES[e.region]}, ${e.name} ${e.year}: the regional mean PM2.5 peaked at ${fmt(h.peak_pm25, 0)} µg/m³ ` +
      `${hourOffsetText(h.peak_hour)}` +
      (rise ? `, ${ratioText(h.ratio)} the ${fmt(h.baseline_pm25)} µg/m³ typical of the days before` : `, no clear rise over the ${fmt(h.baseline_pm25)} µg/m³ of the days before`) +
      ` (${h.stations} station${h.stations === 1 ? "" : "s"}).`
    );
  }
  const d = e.daily;
  if (d.event_day != null && d.before != null) {
    return (
      `${REGION_NAMES[e.region]}, ${e.name} ${e.year}: the daily mean was ${fmt(d.event_day, 0)} µg/m³ against ${fmt(d.before, 0)} µg/m³ ` +
      `the week before (${d.n} station${d.n === 1 ? "" : "s"}; no hourly data kept).`
    );
  }
  return null;
}

export function keralaHeadline(d: KeralaMonsoon): string | null {
  const r = d.rain_vs_pm25;
  if (r.spearman == null || r.rainy_day_median == null || r.dry_day_median == null) return null;
  const cleaner = r.spearman <= -0.2 && r.rainy_day_median < r.dry_day_median;
  return (
    `Across ${d.basis.days} days, ${cleaner ? "rainier days had cleaner air" : "rain and PM2.5 showed"}: ` +
    `${correlationWord(r.spearman)} rank correlation (ρ = ${fmt(r.spearman, 2)}). ` +
    `The median PM2.5 was ${fmt(r.rainy_day_median, 0)} µg/m³ on days with at least 10 mm of rain (${r.rainy_days} days) ` +
    `and ${fmt(r.dry_day_median, 0)} µg/m³ on dry days (${r.dry_days} days).`
  );
}

export function uaeHeadline(d: UaeDust): string | null {
  const x = d.dust_vs_pm25;
  if (x.spearman == null || x.dusty_day_median == null || x.clear_day_median == null) return null;
  const lower = x.dusty_day_median < x.clear_day_median;
  return (
    `On the dustiest quarter of days, the median measured PM2.5 was ${fmt(x.dusty_day_median, 0)} µg/m³, ` +
    `${lower ? "lower than" : "higher than"} the ${fmt(x.clear_day_median, 0)} µg/m³ on the least dusty quarter ` +
    `(${correlationWord(x.spearman)} correlation, ρ = ${fmt(x.spearman, 2)}, ${d.basis.paired_days} days).`
  );
}

export function germanyHeadlines(d: GermanySeasons): string[] {
  const out: string[] = [];
  const withPm = d.comparison.filter((c) => c.pm25.ratio != null);
  const ratios = withPm.map((c) => c.pm25.ratio as number);
  const lo = Math.min(...ratios), hi = Math.max(...ratios);
  if (withPm.length && lo >= 1) {
    out.push(
      `PM2.5 averaged ${lo === hi ? ratioText(lo) : `${ratioText(lo)} to ${ratioText(hi)}`} higher in the heating season (October–March) ` +
        `than in summer, across all ${withPm.length} station groups.`,
    );
  }
  const traffic = d.comparison.find((c) => c.group === "urban traffic");
  const rural = d.comparison.find((c) => c.group === "rural background");
  const t = traffic && mean(traffic.no2.heating, traffic.no2.summer);
  const r = rural && mean(rural.no2.heating, rural.no2.summer);
  if (traffic && t != null && r != null && r > 0) {
    const flat = traffic.no2.ratio != null && Math.abs(traffic.no2.ratio - 1) <= 0.15;
    out.push(
      `NO₂ at urban traffic stations averaged ${fmt(t, 0)} µg/m³, ${ratioText(t / r)} the ${fmt(r, 0)} µg/m³ at rural background stations` +
        (flat ? ` — and barely changed with the season (${ratioText(traffic.no2.ratio)} in winter), pointing to exhaust rather than heating.` : "."),
    );
  }
  return out;
}

export function tamilNaduHeadline(d: TamilNaduLandUse): string | null {
  const ind = d.groups.find((g) => g.use === "industrial");
  const res = d.groups.find((g) => g.use === "residential");
  if (!ind?.so2 || !res?.so2) return null;
  return (
    `Median SO₂ at industrial monitors was ${fmt(ind.so2, 0)} µg/m³, ${ratioText(ind.so2 / res.so2)} the ` +
    `${fmt(res.so2, 0)} µg/m³ at residential monitors (${ind.stations} vs ${res.stations} station${res.stations === 1 ? "" : "s"}).`
  );
}

function mean(a: number | null, b: number | null): number | null {
  return a != null && b != null ? (a + b) / 2 : null;
}
