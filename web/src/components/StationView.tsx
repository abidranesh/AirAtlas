"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useState } from "react";
import { useApi } from "@/lib/api";
import { ageText, fmt, localTime, POLLUTANTS, REGION_NAMES, SCALE_LABELS } from "@/lib/format";
import type { Evaluation, Meta, Scale, Series, StationDetail } from "@/lib/types";
import { useScale } from "@/lib/useScale";
import { AqiBadge, Card, ErrorNote, FreshnessBadge, KindBadge, ScaleToggle, Skeleton } from "./ui";

// Recharts is ~100 KB; load it only when the trends section renders.
const ConcentrationChart = dynamic(() => import("./TrendChart").then((m) => m.ConcentrationChart), {
  ssr: false,
  loading: () => <Skeleton className="h-64" />,
});
const AqiBars = dynamic(() => import("./TrendChart").then((m) => m.AqiBars), {
  ssr: false,
  loading: () => <Skeleton className="h-40" />,
});

const RANGES = ["24h", "7d", "30d", "1y"] as const;
const SCALES: Scale[] = ["local", "eu_eaqi", "who_2021_pm25"];

function statusText(ev: Evaluation): string | null {
  if (ev.freshness === "unavailable") return ev.latest_ts ? `Data unavailable: the last value is ${ageText(ev.age_minutes)}.` : "No data from this station yet.";
  if (!ev.aqi || ev.aqi.status === "insufficient_data") return "Not enough data for this standard yet (it needs a full averaging window).";
  return null;
}

function ScaleCard({ scale, ev, meta, selected, onSelect }: { scale: Scale; ev: Evaluation; meta: Meta; selected: boolean; onSelect: () => void }) {
  const std = ev.aqi ? meta.standards[ev.aqi.standard] : undefined;
  const msg = statusText(ev);
  return (
    <button
      onClick={onSelect}
      aria-pressed={selected}
      className={`rounded-xl border p-4 text-left transition-colors ${
        selected ? "border-neutral-900 ring-1 ring-neutral-900 dark:border-white dark:ring-white" : "border-neutral-200 hover:border-neutral-400 dark:border-neutral-800"
      } bg-white dark:bg-neutral-900`}
    >
      <div className="text-xs text-neutral-500">{scale === "local" ? std?.short_name ?? SCALE_LABELS.local : SCALE_LABELS[scale]}</div>
      {msg ? (
        <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">{msg}</p>
      ) : (
        <div className="mt-2 space-y-1">
          <AqiBadge category={ev.aqi!.category} value={std?.scale.type === "index" ? ev.aqi!.value : undefined} size="lg" />
          {ev.aqi!.extra?.who_multiple !== undefined && (
            <p className="text-sm">{fmt(ev.aqi!.extra.who_multiple)}× the WHO 24-h guideline</p>
          )}
          {ev.aqi!.dominant.length > 0 && (
            <p className="text-xs text-neutral-600 dark:text-neutral-400">
              Driven by {ev.aqi!.dominant.map((p) => POLLUTANTS[p]?.label ?? p).join(", ")}
              {ev.aqi!.status === "partial" && " · partial (no PM data)"}
            </p>
          )}
        </div>
      )}
    </button>
  );
}

export default function StationView({ id }: { id: number }) {
  const [scale, setScale] = useScale(true);
  const [range, setRange] = useState<(typeof RANGES)[number]>("24h");
  const [pollutant, setPollutant] = useState("pm25");
  const meta = useApi<Meta>("/meta");
  const detail = useApi<StationDetail>(`/stations/${id}`);
  const series = useApi<Series>(`/stations/${id}/series?range=${range}&scale=${scale}`, { keepPrevious: true });

  if (detail.error) return <ErrorNote error={detail.error} />;
  const st = detail.data;
  if (!st || !meta.data) return <Skeleton className="h-[70vh]" />;

  const tz = meta.data.regions.find((r) => r.code === st.region)?.timezone ?? "UTC";
  const ev = st.now[scale];
  const std = ev.aqi ? meta.data.standards[ev.aqi.standard] : undefined;
  const cat = ev.aqi?.category ? std?.categories[ev.aqi.category.level - 1] : undefined;
  const available = Object.keys(st.now.local.concentrations ?? {});
  const pollutantOptions = Object.keys(POLLUTANTS).filter((p) => p !== "dust" || available.includes("dust"));

  return (
    <div className="space-y-5">
      <nav className="text-sm text-neutral-500">
        <Link href={`/region/${st.region}${scale !== "local" ? `?scale=${scale}` : ""}`} className="hover:underline">
          {REGION_NAMES[st.region]}
        </Link>
        {st.area && <> / {st.area}</>}
      </nav>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold sm:text-3xl">{st.name}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-neutral-600 dark:text-neutral-400">
            <KindBadge kind={st.kind} />
            {[st.setting, st.station_type].filter(Boolean).join(" · ")}
            {st.now.local.latest_ts && <span>Latest hour: {localTime(st.now.local.latest_ts, tz)}</span>}
            <FreshnessBadge freshness={st.now.local.freshness} age={ageText(st.now.local.age_minutes)} />
          </div>
        </div>
        <ScaleToggle value={scale} options={SCALES} onChange={setScale} />
      </header>

      <div className="grid gap-3 sm:grid-cols-3">
        {SCALES.map((s) => (
          <ScaleCard key={s} scale={s} ev={st.now[s]} meta={meta.data!} selected={s === scale} onSelect={() => setScale(s)} />
        ))}
      </div>

      {st.official && (
        <Card>
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="font-semibold">Official CPCB index</h2>
            <AqiBadge category={st.official.category} value={st.official.value} />
            <span className="text-xs text-neutral-500">reported {localTime(st.official.reported_at, tz)}</span>
          </div>
          <p className="mt-1 text-xs text-neutral-500">{st.official.note}</p>
        </Card>
      )}

      {cat && (
        <Card>
          <h2 className="mb-1 font-semibold">What this means</h2>
          <p className="text-sm">{cat.health}</p>
          {cat.health_sensitive && <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">Sensitive groups: {cat.health_sensitive}</p>}
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
        <Card>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold">Trends</h2>
            <div className="flex flex-wrap gap-2">
              <select
                aria-label="Pollutant"
                value={pollutant}
                onChange={(e) => setPollutant(e.target.value)}
                className="rounded-md border border-neutral-300 bg-transparent px-2 py-1 text-sm dark:border-neutral-700"
              >
                {pollutantOptions.map((p) => (
                  <option key={p} value={p}>
                    {POLLUTANTS[p].label}
                  </option>
                ))}
              </select>
              <div role="tablist" aria-label="Time range" className="inline-flex rounded-md border border-neutral-300 dark:border-neutral-700">
                {RANGES.map((r) => (
                  <button
                    key={r}
                    role="tab"
                    aria-selected={r === range}
                    onClick={() => setRange(r)}
                    className={`px-2.5 py-1 text-sm ${r === range ? "bg-neutral-900 text-white dark:bg-white dark:text-neutral-900" : ""}`}
                  >
                    {r}
                  </button>
                ))}
              </div>
            </div>
          </div>
          {series.error ? (
            <ErrorNote error={series.error} />
          ) : !series.data ? (
            <Skeleton className="h-64" />
          ) : (
            <div className={series.loading ? "opacity-60" : ""}>
              <ConcentrationChart series={series.data} pollutant={pollutant} tz={tz} />
              {series.data.aqi && std && (
                <>
                  <h3 className="mt-4 mb-1 text-sm font-medium">Hourly {std.short_name}</h3>
                  <AqiBars series={series.data} standard={std} tz={tz} />
                </>
              )}
              {series.data.resolution === "daily" && (
                <p className="mt-2 text-xs text-neutral-500">Daily means by local calendar day. Hourly data is kept for 90 days.</p>
              )}
            </div>
          )}
        </Card>

        <div className="space-y-4">
          <Card>
            <h2 className="mb-2 font-semibold">Latest hour</h2>
            {st.now.local.concentrations ? (
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-neutral-500">
                  <tr>
                    <th className="font-normal">Pollutant</th>
                    <th className="text-right font-normal">Value</th>
                    <th className="text-right font-normal">{std?.short_name ?? "Sub-index"}</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(st.now.local.concentrations).map(([p, v]) => {
                    const sub = ev.aqi?.sub_indices?.find((s) => s.pollutant === p);
                    return (
                      <tr key={p} className="border-t border-neutral-100 dark:border-neutral-800">
                        <td className="py-1">{POLLUTANTS[p]?.label ?? p}</td>
                        <td className="py-1 text-right tabular-nums">
                          {fmt(v, p === "co" ? 2 : 1)} <span className="text-xs text-neutral-500">{POLLUTANTS[p]?.unit}</span>
                        </td>
                        <td className="py-1 text-right tabular-nums">
                          {!sub ? "–" : std?.scale.type === "index" ? `${fmt(sub.value, 0)} (${sub.averaging})` : `${std?.categories.find((c) => c.key === sub.category)?.label ?? sub.category} (${sub.averaging})`}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <p className="text-sm text-neutral-500">No recent measurements.</p>
            )}
          </Card>
          <Card>
            <h2 className="mb-2 font-semibold">Sources</h2>
            <ul className="space-y-1 text-sm">
              {st.sources.map((s) => (
                <li key={s.code}>
                  {s.attribution}
                  <span className="block text-xs text-neutral-500">{s.license}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
