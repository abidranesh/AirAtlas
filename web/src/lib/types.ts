// Mirrors the FastAPI responses (api/airatlas_api). Keep in sync with docs/phase-4-api.md.

export const REGION_CODES = ["tamil_nadu", "kerala", "uae", "germany"] as const;
export type RegionCode = (typeof REGION_CODES)[number];
export type Scale = "local" | "eu_eaqi" | "who_2021_pm25";
export type CommonScale = Exclude<Scale, "local">;
export type StationKind = "reference" | "low_cost" | "modeled";
export type Freshness = "fresh" | "stale" | "unavailable";

export interface Category {
  key: string;
  label: string;
  color: string;
  level: number;
}

export interface SubIndex {
  pollutant: string;
  averaging: string;
  concentration: number;
  value: number;
  category: string;
  beyond_scale?: boolean;
}

export interface Aqi {
  standard: string;
  status: "ok" | "partial" | "insufficient_data";
  value: number | null;
  level: number | null;
  category: Category | null;
  dominant: string[];
  extra?: { who_multiple?: number };
  sub_indices?: SubIndex[];
  notes?: string[];
  health?: { general: string; sensitive: string | null };
}

export interface Official {
  source: "cpcb";
  standard: string;
  value: number;
  category: Category;
  dominant: string[];
  reported_at: string;
  sub_indices: Record<string, number>;
  note: string;
}

export interface StationBase {
  id: number;
  name: string;
  city: string | null;
  area_id: number | null;
  area: string | null;
  kind: StationKind;
  setting: string | null;
  station_type: string | null;
  lat: number;
  lon: number;
  region: RegionCode;
}

export interface Evaluation {
  latest_ts: string | null;
  age_minutes: number | null;
  freshness: Freshness;
  aqi: Aqi | null;
  concentrations: Record<string, number> | null;
}

export type StationLatest = StationBase & Evaluation & { official: Official | null };

export interface AreaSummary {
  area_id: number;
  name: string;
  value: number | null;
  basis: "measured" | "modeled" | null;
  n_stations: number;
  category?: Category;
}

export interface RegionLatest {
  region: { code: RegionCode; name: string; timezone: string; local_standard: string };
  scale: Scale;
  standard: string;
  generated_at: string;
  stations: StationLatest[];
  areas: AreaSummary[];
}

export interface StandardCategory extends Category {
  index_range: [number, number] | null;
  health: string;
  health_sensitive: string | null;
}

export interface StandardInfo {
  name: string;
  short_name: string;
  version: string;
  scale: { type: "index" | "levels"; min: number; max: number };
  categories: StandardCategory[];
  sources: { title: string; url: string; accessed: string }[];
}

export interface RegionInfo {
  id: number;
  code: RegionCode;
  name: string;
  country_code: string;
  timezone: string;
  local_standard: string;
  bbox: { type: "Polygon"; coordinates: number[][][] };
  reference_stations: number;
  low_cost_stations: number;
  modeled_points: number;
}

export interface Meta {
  regions: RegionInfo[];
  standards: Record<string, StandardInfo>;
  common_scales: CommonScale[];
  sources: { code: string; name: string; kind: string; license: string; attribution: string; url: string }[];
}

export interface StationDetail extends StationBase {
  first_seen_at: string;
  last_seen_at: string;
  sources: { code: string; name: string; kind: string; license: string; attribution: string }[];
  now: Record<Scale, Evaluation>;
  official: Official | null;
}

export interface SeriesPoint {
  ts?: string;
  day?: string;
  [pollutant: string]: number | string | undefined;
}

export interface Series {
  station: { id: number; name: string; region: RegionCode; kind: StationKind };
  range: "24h" | "7d" | "30d" | "1y";
  resolution: "hourly" | "daily";
  since: string;
  points: SeriesPoint[];
  standard?: string;
  aqi?: { ts: string; value: number | null; level: number | null; status: string; dominant: string[] }[];
}

export interface CompareRegion {
  featured_area: AreaSummary | null;
  best_areas: AreaSummary[];
  worst_areas: AreaSummary[];
  stations_with_data: number;
  stations_total: number;
}

export interface MonthlyRow {
  region: RegionCode;
  area: string | null;
  month: string;
  pm25: number;
  stations: number;
  station_days: number;
}

export interface Compare {
  scale: CommonScale;
  generated_at: string;
  now: Record<RegionCode, CompareRegion>;
  monthly_pm25: { who_annual_guideline: number; regions: MonthlyRow[]; featured_areas: MonthlyRow[] };
}

export interface SearchResult {
  type: "station" | "area";
  id: number;
  name: string;
  context: string | null;
  region: RegionCode;
  lat: number;
  lon: number;
}

export type NearestStation = StationBase & Evaluation & { distance_km: number };
