"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fmt, NO_DATA_COLOR, POLLUTANTS } from "@/lib/format";
import type { AnomalyEpisode, Series, StandardInfo } from "@/lib/types";

function tickFormatter(range: Series["range"], tz: string) {
  const opts: Intl.DateTimeFormatOptions =
    range === "24h"
      ? { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }
      : range === "1y"
        ? { month: "short" }
        : { day: "numeric", month: "short" };
  const f = new Intl.DateTimeFormat("en-GB", { ...opts, timeZone: tz });
  return (v: string) => f.format(new Date(v));
}

export function seriesKey(series: Series, pollutant: string): string {
  return series.resolution === "daily" ? `${pollutant}_mean` : pollutant;
}

export function ConcentrationChart({
  series,
  pollutant,
  tz,
  episodes = [],
}: {
  series: Series;
  pollutant: string;
  tz: string;
  episodes?: AnomalyEpisode[];
}) {
  const key = seriesKey(series, pollutant);
  const x = series.resolution === "daily" ? "day" : "ts";
  const points = series.points.filter((p) => p[key] !== undefined && p[key] !== null);
  const meta = POLLUTANTS[pollutant];
  if (points.length === 0) {
    return <p className="py-10 text-center text-sm text-neutral-500">No {meta?.label ?? pollutant} data for this period.</p>;
  }
  const fmtTick = tickFormatter(series.range, tz);
  return (
    <div className="h-64 w-full" role="img" aria-label={`${meta?.label} over the last ${series.range}`}>
      <ResponsiveContainer>
        <LineChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
          <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.3} />
          <XAxis dataKey={x} tickFormatter={fmtTick} minTickGap={32} fontSize={12} />
          <YAxis fontSize={12} width={48} />
          <Tooltip
            labelFormatter={(v) => new Date(String(v)).toLocaleString("en-GB", { timeZone: tz, dateStyle: "medium", ...(x === "ts" ? { timeStyle: "short" } : {}) })}
            formatter={(v) => [`${fmt(Number(v))} ${meta?.unit ?? ""}`, series.resolution === "daily" ? `${meta?.label} daily mean` : meta?.label]}
          />
          {pollutant === "pm25" && series.resolution === "daily" && (
            <ReferenceLine y={15} stroke="#2E7D32" strokeDasharray="4 4" label={{ value: "WHO 24-h guideline", fontSize: 11, position: "insideTopRight" }} />
          )}
          {series.resolution === "hourly" &&
            episodes
              .filter((e) => e.pollutant === pollutant && e.ends_at >= series.since)
              .map((e) => {
                // Snap to the chart's own x values so the shaded band lines up with the plotted hours.
                const xs = points.map((p) => String(p.ts));
                const x1 = xs.find((t) => t >= e.starts_at) ?? e.starts_at;
                const x2 = [...xs].reverse().find((t) => t <= e.ends_at) ?? e.ends_at;
                return <ReferenceArea key={e.id} x1={x1} x2={x2} fill="#dc2626" fillOpacity={0.12} ifOverflow="hidden" />;
              })}
          <Line type="monotone" dataKey={key} stroke="#0369a1" dot={false} strokeWidth={2} connectNulls={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function AqiBars({ series, standard, tz }: { series: Series; standard: StandardInfo; tz: string }) {
  const rows = (series.aqi ?? []).map((a) => ({ ...a, y: a.value ?? 0 }));
  if (!rows.some((r) => r.value !== null)) {
    return <p className="py-6 text-center text-sm text-neutral-500">Not enough data to compute {standard.short_name} for this period.</p>;
  }
  const colorFor = (level: number | null) => (level ? standard.categories[level - 1]?.color : NO_DATA_COLOR) ?? NO_DATA_COLOR;
  const fmtTick = tickFormatter(series.range, tz);
  return (
    <div className="h-40 w-full" role="img" aria-label={`Hourly ${standard.short_name}`}>
      <ResponsiveContainer>
        <BarChart data={rows} margin={{ top: 4, right: 12, bottom: 0, left: -12 }} barCategoryGap={1}>
          <XAxis dataKey="ts" tickFormatter={fmtTick} minTickGap={32} fontSize={12} />
          <YAxis fontSize={12} width={48} allowDecimals={false} />
          <Tooltip
            labelFormatter={(v) => new Date(String(v)).toLocaleString("en-GB", { timeZone: tz, dateStyle: "medium", timeStyle: "short" })}
            formatter={(_v, _n, item) => {
              const p = item.payload as (typeof rows)[number];
              if (p.value === null) return ["not enough data", standard.short_name];
              const cat = p.level ? standard.categories[p.level - 1] : undefined;
              return [`${standard.scale.type === "index" ? `${p.value} ` : ""}${cat?.label ?? ""}`, standard.short_name];
            }}
          />
          <Bar dataKey="y" isAnimationActive={false}>
            {rows.map((r) => (
              <Cell key={r.ts} fill={colorFor(r.level)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
