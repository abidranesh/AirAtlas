import type * as Leaflet from "leaflet";
import { NO_DATA_COLOR } from "./format";
import type { AreaSummary, StationLatest } from "./types";

// Pure styling rules for the region map (unit-tested; no Leaflet runtime needed).

/** Marker colour: our computed AQI, else CPCB's published index (India), else grey. */
export function stationColor(s: StationLatest): string {
  return s.aqi?.category?.color ?? s.official?.category.color ?? NO_DATA_COLOR;
}

export function markerStyle(s: StationLatest): Leaflet.CircleMarkerOptions {
  const color = stationColor(s);
  const hasValue = color !== NO_DATA_COLOR;
  if (s.kind === "modeled") return { radius: 5, color, weight: 2.5, fillOpacity: 0, opacity: hasValue ? 0.9 : 0.5 };
  if (s.kind === "low_cost") return { radius: 6, color: "#111827", weight: 1, dashArray: "2 2", fillColor: color, fillOpacity: 0.9 };
  return { radius: 7, color: "#111827", weight: 1.2, fillColor: color, fillOpacity: hasValue ? 0.95 : 0.55 };
}

export function areaStyle(a: AreaSummary | undefined): Leaflet.PathOptions {
  const modeled = a?.basis === "modeled";
  return {
    fillColor: a?.category?.color ?? NO_DATA_COLOR,
    fillOpacity: a?.value == null ? 0.1 : modeled ? 0.22 : 0.42,
    color: "#475569",
    weight: 1,
    dashArray: modeled ? "4 4" : undefined,
  };
}

