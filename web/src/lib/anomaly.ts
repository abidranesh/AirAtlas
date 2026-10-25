import type { RegionAnomalies } from "./types";

/** Display names and colours for cause hints (kinds come from ml/src/airatlas_ml/causes.py). */
export const HINTS: Record<string, { label: string; icon: string; color: string }> = {
  fire_upwind: { label: "Fires upwind", icon: "🔥", color: "#ea580c" },
  fire_nearby: { label: "Fires nearby", icon: "🔥", color: "#fb923c" },
  industrial_heat_upwind: { label: "Industrial heat upwind", icon: "🏭", color: "#78716c" },
  dust: { label: "Desert dust", icon: "🏜️", color: "#ca8a04" },
  festival: { label: "Festival / fireworks", icon: "🎆", color: "#c026d3" },
  stagnation: { label: "Stagnant air", icon: "🌫️", color: "#64748b" },
  regional: { label: "Area-wide", icon: "🗺️", color: "#2563eb" },
  local: { label: "Local source", icon: "📍", color: "#0d9488" },
  traffic: { label: "Traffic site", icon: "🚗", color: "#475569" },
  possible_artefact: { label: "Possible instrument artefact", icon: "⚠️", color: "#a3a3a3" },
  none: { label: "No clear cause", icon: "•", color: "#d4d4d4" },
};

export function hintInfo(kind: string | null) {
  return HINTS[kind ?? "none"] ?? { label: kind ?? "Other", icon: "•", color: "#d4d4d4" };
}

/** per_day rows -> one row per day with a count column per top hint, for a stacked bar chart. */
export function pivotPerDay(perDay: RegionAnomalies["per_day"]): { rows: Record<string, number | string>[]; kinds: string[] } {
  const byDay = new Map<string, Record<string, number | string>>();
  const kinds = new Set<string>();
  for (const r of perDay) {
    const k = r.top_hint ?? "none";
    kinds.add(k);
    const row = byDay.get(r.day) ?? { day: r.day };
    row[k] = ((row[k] as number | undefined) ?? 0) + r.n;
    byDay.set(r.day, row);
  }
  const order = Object.keys(HINTS);
  return {
    rows: [...byDay.values()].sort((a, b) => String(a.day).localeCompare(String(b.day))),
    kinds: [...kinds].sort((a, b) => order.indexOf(a) - order.indexOf(b)),
  };
}
