"use client";

import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { hintInfo, pivotPerDay } from "@/lib/anomaly";
import type { RegionAnomalies } from "@/lib/types";

export function AnomalyTimeline({ data }: { data: RegionAnomalies }) {
  const { rows, kinds } = pivotPerDay(data.per_day);
  if (rows.length === 0) return <p className="py-6 text-center text-sm text-neutral-500">No pollution spikes detected in this period.</p>;
  const day = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
  return (
    <div className="h-44 w-full" role="img" aria-label={`Pollution spikes per day over the last ${data.days} days, by most likely cause`}>
      <ResponsiveContainer>
        <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
          <XAxis dataKey="day" tickFormatter={(v) => day.format(new Date(v))} fontSize={11} minTickGap={24} />
          <YAxis allowDecimals={false} fontSize={11} width={40} />
          <Tooltip labelFormatter={(v) => day.format(new Date(String(v)))} formatter={(v, name) => [v, hintInfo(String(name)).label]} />
          {kinds.map((k) => (
            <Bar key={k} dataKey={k} stackId="a" fill={hintInfo(k).color} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
