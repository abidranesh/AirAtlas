"use client";

import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmt, REGION_NAMES } from "@/lib/format";
import { FEATURED_LABEL } from "@/lib/regions";
import { pivotMonthly } from "@/lib/compare";
import type { MonthlyRow, RegionCode } from "@/lib/types";

const COLORS: Record<RegionCode, string> = { tamil_nadu: "#b45309", kerala: "#15803d", uae: "#be123c", germany: "#1d4ed8" };

export default function MonthlyChart({ rows, guideline }: { rows: MonthlyRow[]; guideline: number }) {
  const data = pivotMonthly(rows);
  const regions = [...new Set(rows.map((r) => r.region))];
  if (data.length === 0) {
    return <p className="py-10 text-center text-sm text-neutral-500">Monthly averages appear once daily history has been loaded.</p>;
  }
  const month = new Intl.DateTimeFormat("en-GB", { month: "short", year: "2-digit", timeZone: "UTC" });
  return (
    <div className="h-72 w-full" role="img" aria-label="Monthly mean PM2.5 for the featured areas">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
          <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.3} />
          <XAxis dataKey="month" tickFormatter={(v) => month.format(new Date(v))} fontSize={12} />
          <YAxis fontSize={12} width={48} unit="" />
          <Tooltip labelFormatter={(v) => month.format(new Date(String(v)))} formatter={(v, name) => [`${fmt(Number(v))} µg/m³`, FEATURED_LABEL[name as RegionCode] ?? REGION_NAMES[name as RegionCode]]} />
          <Legend formatter={(name) => FEATURED_LABEL[name as RegionCode]} />
          <ReferenceLine y={guideline} stroke="#2E7D32" strokeDasharray="4 4" label={{ value: `WHO annual guideline (${guideline})`, fontSize: 11, position: "insideTopRight" }} />
          {regions.map((r) => (
            <Line key={r} dataKey={r} stroke={COLORS[r]} strokeWidth={2} dot={{ r: 3 }} connectNulls={false} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
