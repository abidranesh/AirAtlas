"use client";

import type { ReactElement } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fmt } from "@/lib/format";
import type { FestivalEvent, GermanPollutant, GermanySeasons, KeralaMonsoon, LandUse, TamilNaduLandUse, UaeDust } from "@/lib/insights";

const UG = "µg/m³";
const monthFmt = new Intl.DateTimeFormat("en-GB", { month: "short", year: "2-digit", timeZone: "UTC" });
const dayFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
const grid = <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.3} />;

function Frame({ label, children, className = "h-72" }: { label: string; children: ReactElement; className?: string }) {
  return (
    <div className={`w-full ${className}`} role="img" aria-label={label}>
      <ResponsiveContainer>{children}</ResponsiveContainer>
    </div>
  );
}

export function FestivalChart({ event }: { event: FestivalEvent }) {
  const hourly = event.hourly;
  return (
    <Frame label={`Hourly regional mean PM2.5 around ${event.name} ${event.year}`}>
      <LineChart data={event.series} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
        {grid}
        <XAxis
          dataKey="h"
          type="number"
          domain={["dataMin", "dataMax"]}
          ticks={[-72, -48, -24, 0, 24, 48, 72, 96]}
          tickFormatter={(h) => (h === 0 ? "0 h" : `${h > 0 ? "+" : ""}${h} h`)}
          fontSize={12}
        />
        <YAxis fontSize={12} width={48} />
        <Tooltip
          labelFormatter={(h) => `${Number(h) > 0 ? "+" : ""}${h} h from the festival hour`}
          formatter={(v, name, item) => [`${fmt(Number(v))} ${UG} (${item.payload.n} stations)`, name === "pm25" ? "PM2.5" : "PM10"]}
        />
        <ReferenceLine x={0} stroke="#be123c" strokeDasharray="4 4" label={{ value: "festival hour", fontSize: 11, position: "insideTopLeft" }} />
        {hourly.baseline_pm25 != null && (
          <ReferenceLine y={hourly.baseline_pm25} stroke="#737373" strokeDasharray="2 4" label={{ value: "baseline", fontSize: 11, position: "insideBottomRight" }} />
        )}
        <Line dataKey="pm25" name="pm25" stroke="#b45309" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
      </LineChart>
    </Frame>
  );
}

export function KeralaChart({ monthly }: { monthly: KeralaMonsoon["monthly"] }) {
  return (
    <Frame label="Monthly rainfall and mean PM2.5 in Kerala" className="h-80">
      <ComposedChart data={monthly} margin={{ top: 8, right: 0, bottom: 0, left: -12 }}>
        {grid}
        <XAxis dataKey="month" tickFormatter={(m) => monthFmt.format(new Date(`${m}-01`))} fontSize={12} />
        <YAxis yAxisId="pm" fontSize={12} width={48} />
        <YAxis yAxisId="rain" orientation="right" fontSize={12} width={48} />
        <Tooltip
          labelFormatter={(m) => monthFmt.format(new Date(`${m}-01`))}
          formatter={(v, name) => (name === "Rain" ? [`${fmt(Number(v), 0)} mm`, name] : [`${fmt(Number(v))} ${UG}`, name])}
        />
        <Legend />
        <Bar yAxisId="rain" dataKey="rain_mm" name="Rain" fill="#38bdf8" fillOpacity={0.6} isAnimationActive={false} />
        <Line yAxisId="pm" dataKey="pm25" name="PM2.5" stroke="#b45309" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
      </ComposedChart>
    </Frame>
  );
}

export function UaeScatter({ daily }: { daily: UaeDust["daily"] }) {
  const points = daily.filter((d) => d.dust != null && d.pm25 != null);
  return (
    <Frame label="Daily modeled dust against measured PM2.5 in the UAE">
      <ScatterChart margin={{ top: 8, right: 12, bottom: 16, left: -12 }}>
        {grid}
        <XAxis dataKey="dust" type="number" name="Dust" unit="" fontSize={12} label={{ value: `modeled dust, ${UG}`, fontSize: 11, position: "insideBottom", offset: -10 }} />
        <YAxis dataKey="pm25" type="number" name="PM2.5" fontSize={12} width={48} />
        <Tooltip
          formatter={(v, name) => [`${fmt(Number(v))} ${UG}`, name]}
          labelFormatter={() => ""}
        />
        <Scatter data={points} fill="#be123c" fillOpacity={0.7} isAnimationActive={false} />
      </ScatterChart>
    </Frame>
  );
}

export function UaeTimeline({ daily }: { daily: UaeDust["daily"] }) {
  return (
    <Frame label="Daily measured PM2.5 and modeled dust in the UAE">
      <LineChart data={daily} margin={{ top: 8, right: 0, bottom: 0, left: -12 }}>
        {grid}
        <XAxis dataKey="day" tickFormatter={(d) => dayFmt.format(new Date(d))} fontSize={12} minTickGap={24} />
        <YAxis yAxisId="pm" fontSize={12} width={48} />
        <YAxis yAxisId="dust" orientation="right" fontSize={12} width={48} />
        <Tooltip labelFormatter={(d) => dayFmt.format(new Date(String(d)))} formatter={(v, name) => [`${fmt(Number(v))} ${UG}`, name]} />
        <Legend />
        <Line yAxisId="dust" dataKey="dust" name="Dust (modeled)" stroke="#d97706" strokeDasharray="4 2" dot={false} isAnimationActive={false} />
        <Line yAxisId="pm" dataKey="pm25" name="PM2.5 (measured)" stroke="#be123c" strokeWidth={2} dot={false} isAnimationActive={false} />
      </LineChart>
    </Frame>
  );
}

export const GROUP_COLORS: Record<string, string> = {
  "urban traffic": "#be123c",
  "urban background": "#b45309",
  "suburban background": "#1d4ed8",
  "rural background": "#15803d",
};

export function GermanyChart({ monthly, pollutant }: { monthly: GermanySeasons["monthly"]; pollutant: GermanPollutant }) {
  const byMonth = new Map<string, Record<string, number | string | null>>();
  for (const r of monthly) {
    const row = byMonth.get(r.month) ?? { month: r.month };
    row[r.group] = r[pollutant];
    byMonth.set(r.month, row);
  }
  const data = [...byMonth.values()].sort((a, b) => String(a.month).localeCompare(String(b.month)));
  const groups = Object.keys(GROUP_COLORS).filter((g) => monthly.some((r) => r.group === g));
  return (
    <Frame label="Monthly mean concentration by German station group" className="h-80">
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
        {grid}
        <XAxis dataKey="month" tickFormatter={(m) => monthFmt.format(new Date(m))} fontSize={12} minTickGap={16} />
        <YAxis fontSize={12} width={48} />
        <Tooltip labelFormatter={(m) => monthFmt.format(new Date(String(m)))} formatter={(v, name) => [`${fmt(Number(v))} ${UG}`, name]} />
        <Legend />
        {groups.map((g) => (
          <Line key={g} dataKey={g} stroke={GROUP_COLORS[g]} strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
        ))}
      </LineChart>
    </Frame>
  );
}

const USE_COLORS: Record<LandUse, string> = { industrial: "#7c3aed", residential: "#15803d" };

export function DiurnalChart({ diurnal, pollutant }: { diurnal: TamilNaduLandUse["diurnal"]; pollutant: "so2" | "pm25" | "no2" }) {
  const data = Array.from({ length: 24 }, (_, hour) => {
    const row: Record<string, number | null> = { hour };
    for (const r of diurnal.filter((x) => x.hour === hour)) row[r.use] = r[pollutant];
    return row;
  });
  const uses = (Object.keys(USE_COLORS) as LandUse[]).filter((u) => diurnal.some((r) => r.use === u));
  return (
    <Frame label="Median concentration by local hour of day, industrial vs residential monitors">
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
        {grid}
        <XAxis dataKey="hour" ticks={[0, 3, 6, 9, 12, 15, 18, 21]} tickFormatter={(h) => `${String(h).padStart(2, "0")}:00`} fontSize={12} />
        <YAxis fontSize={12} width={48} />
        <Tooltip labelFormatter={(h) => `${String(h).padStart(2, "0")}:00 IST`} formatter={(v, name) => [`${fmt(Number(v))} ${UG}`, name]} />
        <Legend />
        {uses.map((u) => (
          <Line key={u} dataKey={u} stroke={USE_COLORS[u]} strokeWidth={2} dot={false} isAnimationActive={false} />
        ))}
      </LineChart>
    </Frame>
  );
}
