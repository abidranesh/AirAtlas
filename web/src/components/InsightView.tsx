"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { useApi } from "@/lib/api";
import { fmt, REGION_NAMES } from "@/lib/format";
import {
  correlationWord,
  festivalHeadline,
  germanyHeadlines,
  hasFestivalData,
  INSIGHTS,
  keralaHeadline,
  ratioText,
  tamilNaduHeadline,
  uaeHeadline,
  type FestivalEvent,
  type Festivals,
  type GermanPollutant,
  type GermanySeasons,
  type InsightSlug,
  type KeralaMonsoon,
  type KeralaSeason,
  type TamilNaduLandUse,
  type UaeDust,
} from "@/lib/insights";
import { Card, ErrorNote, Skeleton } from "./ui";

// Recharts is heavy: one lazily loaded chunk for all insight charts (next/dynamic needs literal options).
const charts = () => import("./InsightCharts");
const FestivalChart = dynamic(() => charts().then((m) => m.FestivalChart), { ssr: false, loading: () => <Skeleton className="h-72" /> });
const KeralaChart = dynamic(() => charts().then((m) => m.KeralaChart), { ssr: false, loading: () => <Skeleton className="h-80" /> });
const UaeScatter = dynamic(() => charts().then((m) => m.UaeScatter), { ssr: false, loading: () => <Skeleton className="h-72" /> });
const UaeTimeline = dynamic(() => charts().then((m) => m.UaeTimeline), { ssr: false, loading: () => <Skeleton className="h-72" /> });
const GermanyChart = dynamic(() => charts().then((m) => m.GermanyChart), { ssr: false, loading: () => <Skeleton className="h-80" /> });
const DiurnalChart = dynamic(() => charts().then((m) => m.DiurnalChart), { ssr: false, loading: () => <Skeleton className="h-72" /> });

const UG = "µg/m³";
const th = "px-2 py-1.5 text-left font-medium";
const td = "px-2 py-1.5 tabular-nums";

function Headline({ children }: { children: ReactNode }) {
  return <p className="text-base leading-relaxed text-neutral-800 sm:text-lg dark:text-neutral-200">{children}</p>;
}

function Caveat({ children }: { children: ReactNode }) {
  return <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-950 dark:bg-amber-950 dark:text-amber-100">{children}</p>;
}

function Method({ items }: { items: [string, ReactNode][] }) {
  return (
    <Card>
      <h2 className="font-semibold">How this was computed</h2>
      <dl className="mt-2 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
        {items.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-neutral-500">{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

function Toggle<T extends string>({ value, options, onChange, label }: { value: T; options: [T, string][]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-1">
      {options.map(([v, text]) => (
        <button
          key={v}
          type="button"
          aria-pressed={v === value}
          onClick={() => onChange(v)}
          className={`rounded-full border px-3 py-1 text-sm ${
            v === value ? "border-sky-700 bg-sky-700 text-white" : "border-neutral-300 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
          }`}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

const eventKey = (e: FestivalEvent) => `${e.label}:${e.region}`;

function FestivalsInsight({ d }: { d: Festivals }) {
  const usable = d.events.filter(hasFestivalData);
  const withHourly = usable.filter((e) => e.series.length > 0);
  // Lead with the sharpest rise backed by several stations; a single monitor is an anecdote.
  const byRatio = [...withHourly].sort((a, b) => (b.hourly.ratio ?? 0) - (a.hourly.ratio ?? 0));
  const best = byRatio.find((e) => e.hourly.stations >= 3) ?? byRatio[0];
  const [selected, setSelected] = useState<string | null>(null);
  const ev = withHourly.find((e) => eventKey(e) === selected) ?? best;
  const missing = d.events.length - usable.length;
  return (
    <>
      {best && <Headline>{festivalHeadline(best)}</Headline>}
      {ev && (
        <Card className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold">
              {ev.name} {ev.year} · {REGION_NAMES[ev.region]}
            </h2>
            <label className="text-sm">
              <span className="sr-only">Festival window</span>
              <select
                value={eventKey(ev)}
                onChange={(e) => setSelected(e.target.value)}
                className="rounded border border-neutral-300 bg-white px-2 py-1 dark:border-neutral-700 dark:bg-neutral-900"
              >
                {withHourly.map((e) => (
                  <option key={eventKey(e)} value={eventKey(e)}>
                    {e.name} {e.year} · {REGION_NAMES[e.region]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <FestivalChart event={ev} />
          <p className="text-sm text-neutral-600 dark:text-neutral-400">{festivalHeadline(ev)}</p>
        </Card>
      )}
      <Card>
        <h2 className="font-semibold">Every festival window with data</h2>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-neutral-200 dark:border-neutral-800">
              <tr>
                <th className={th}>Festival</th>
                <th className={th}>Region</th>
                <th className={th}>Hourly peak</th>
                <th className={th}>vs baseline</th>
                <th className={th}>Day mean</th>
                <th className={th}>vs week before</th>
                <th className={th}>Stations</th>
              </tr>
            </thead>
            <tbody>
              {usable.map((e) => (
                <tr key={eventKey(e)} className="border-b border-neutral-100 last:border-0 dark:border-neutral-800">
                  <td className="px-2 py-1.5">
                    {e.name} {e.year}
                  </td>
                  <td className="px-2 py-1.5">{REGION_NAMES[e.region]}</td>
                  <td className={td}>{e.hourly.peak_pm25 != null ? `${fmt(e.hourly.peak_pm25, 0)} ${UG}` : "–"}</td>
                  <td className={td}>{ratioText(e.hourly.ratio)}</td>
                  <td className={td}>{e.daily.event_day != null ? `${fmt(e.daily.event_day, 0)} ${UG}` : "–"}</td>
                  <td className={td}>{ratioText(e.daily.ratio)}</td>
                  <td className={td}>{Math.max(e.hourly.stations, e.daily.n)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {missing > 0 && (
          <p className="mt-2 text-xs text-neutral-500">
            {missing} other festival window{missing === 1 ? " has" : "s have"} no measurements kept (before a source began reporting, or not yet archived). They
            are left out rather than estimated.
          </p>
        )}
      </Card>
      <Caveat>
        A single station can dominate a window: rows with one station are anecdotes, not regional evidence. Weather also shapes each night (a still
        night traps smoke, a windy one clears it), so ratios are not a measure of how many fireworks were lit.
      </Caveat>
      <Method
        items={[
          ["Alignment", d.method.alignment],
          ["Baseline", d.method.baseline],
          ["Peak", d.method.peak],
          ["Daily", d.method.daily],
          ["Stations", "measured stations only (no model points); hourly data is kept beyond 90 days only for these festival windows"],
        ]}
      />
    </>
  );
}

const SEASONS: KeralaSeason[] = ["Winter", "Pre-monsoon", "Southwest monsoon", "Northeast monsoon"];
const SEASON_MONTHS: Record<KeralaSeason, string> = {
  Winter: "Jan–Feb",
  "Pre-monsoon": "Mar–May",
  "Southwest monsoon": "Jun–Sep",
  "Northeast monsoon": "Oct–Dec",
};

function KeralaInsight({ d }: { d: KeralaMonsoon }) {
  const headline = keralaHeadline(d);
  return (
    <>
      {headline && <Headline>{headline}</Headline>}
      <Card>
        <h2 className="font-semibold">Monthly rain and PM2.5</h2>
        <KeralaChart monthly={d.monthly} />
      </Card>
      <Card>
        <h2 className="font-semibold">By IMD season</h2>
        <div className="mt-2 grid gap-3 sm:grid-cols-4">
          {SEASONS.map((s) => {
            const v = d.by_season[s];
            return (
              <div key={s} className="rounded-lg border border-neutral-200 p-3 dark:border-neutral-800">
                <p className="text-sm font-medium">{s}</p>
                <p className="text-xs text-neutral-500">{SEASON_MONTHS[s]}</p>
                <p className="mt-2 text-2xl font-semibold tabular-nums">
                  {fmt(v?.pm25_median, 0)} <span className="text-sm font-normal text-neutral-500">{UG}</span>
                </p>
                <p className="text-xs text-neutral-600 dark:text-neutral-400">
                  median PM2.5 · {fmt(v?.rain_mm_per_day)} mm rain/day · {v?.days ?? 0} days
                </p>
              </div>
            );
          })}
        </div>
      </Card>
      <Caveat>
        Correlation is not cause: monsoon months can also bring stronger winds and change emissions such as open burning. Rain here is a
        reanalysis (ERA5), averaged across districts, not a rain gauge next to each monitor.
      </Caveat>
      <Method
        items={[
          ["Period", `${d.basis.first ?? "–"} to ${d.basis.last ?? "–"} (${d.basis.days} days, up to ${d.basis.max_stations} stations)`],
          ["PM", d.basis.pm],
          ["Rain", d.basis.rain],
          ["Correlation", "Spearman rank correlation of daily rain vs daily PM2.5; rainy ≥ 10 mm, dry < 1 mm"],
          ["Seasons", "India Meteorological Department convention"],
        ]}
      />
    </>
  );
}

function UaeInsight({ d }: { d: UaeDust }) {
  const headline = uaeHeadline(d);
  const x = d.dust_vs_pm25;
  return (
    <>
      {headline && <Headline>{headline}</Headline>}
      <div className="grid gap-3 lg:grid-cols-2">
        <Card>
          <h2 className="font-semibold">Each day: dust vs PM2.5</h2>
          <UaeScatter daily={d.daily} />
        </Card>
        <Card>
          <h2 className="font-semibold">Last {d.basis.days} days</h2>
          <UaeTimeline daily={d.daily} />
        </Card>
      </div>
      <Card className="space-y-2">
        <h2 className="font-semibold">What it means</h2>
        <p className="text-sm">
          Desert dust is mostly coarse: it shows up in PM10, which the UAE&apos;s open sensors don&apos;t measure.
          {x.wind_vs_dust != null && x.wind_vs_dust >= 0.2
            ? ` Dusty days here were also windy days (wind vs dust: ${correlationWord(x.wind_vs_dust)}, ρ = ${fmt(x.wind_vs_dust, 2)}), and wind can disperse the fine urban particles that PM2.5 sensors do see.`
            : " A high modeled dust load therefore need not raise the PM2.5 these sensors report."}
        </p>
        <p className="text-sm">
          Of {d.spikes.total} PM2.5 spikes flagged in the UAE, {d.spikes.with_dust_hint} came with a dust hint (modeled dust at least 1.5× its weekly median).
        </p>
      </Card>
      {d.spikes.top.length > 0 && (
        <Card>
          <h2 className="font-semibold">Largest spikes where dust was the leading hint</h2>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-neutral-200 dark:border-neutral-800">
                <tr>
                  <th className={th}>Sensor</th>
                  <th className={th}>When</th>
                  <th className={th}>PM2.5 peak</th>
                  <th className={th}>Usual</th>
                  <th className={th}>Dust peak (modeled)</th>
                </tr>
              </thead>
              <tbody>
                {d.spikes.top.map((s) => (
                  <tr key={`${s.station}${s.peak_at}`} className="border-b border-neutral-100 last:border-0 dark:border-neutral-800">
                    <td className="px-2 py-1.5">{s.station}</td>
                    <td className="px-2 py-1.5 whitespace-nowrap">
                      {new Date(s.peak_at).toLocaleString("en-GB", { timeZone: "Asia/Dubai", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })} GST
                    </td>
                    <td className={td}>{fmt(s.peak, 0)}</td>
                    <td className={td}>{fmt(s.baseline, 0)}</td>
                    <td className={td}>{fmt(s.dust_max, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      <Caveat>
        No open, measured PM10 exists for the UAE, so dust here is a model estimate (CAMS) and the PM2.5 is from low-cost sensors. Treat this as a
        comparison of two different instruments, not a measured dust study.
      </Caveat>
      <Method
        items={[
          ["Period", `${d.basis.first ?? "–"} to ${d.basis.last ?? "–"} (${d.basis.paired_days} days with both values)`],
          ["Measured", d.basis.measured],
          ["Modeled", d.basis.modeled],
          ["Dusty / clear", `top quarter of days by dust (≥ ${fmt(x.thresholds.dusty_q3, 0)} ${UG}) vs bottom quarter (≤ ${fmt(x.thresholds.clear_q1, 0)} ${UG})`],
        ]}
      />
    </>
  );
}

const GERMAN_POLLUTANTS: [GermanPollutant, string][] = [
  ["pm25", "PM2.5"],
  ["no2", "NO₂"],
  ["pm10", "PM10"],
];

function GermanyInsight({ d }: { d: GermanySeasons }) {
  const [p, setP] = useState<GermanPollutant>("pm25");
  return (
    <>
      {germanyHeadlines(d).map((h) => (
        <Headline key={h}>{h}</Headline>
      ))}
      <Card className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">Monthly means by station type</h2>
          <Toggle label="Pollutant" value={p} options={GERMAN_POLLUTANTS} onChange={setP} />
        </div>
        <GermanyChart monthly={d.monthly} pollutant={p} />
      </Card>
      <Card>
        <h2 className="font-semibold">Heating season vs summer</h2>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-neutral-200 dark:border-neutral-800">
              <tr>
                <th className={th}>Station group</th>
                <th className={th}>Stations</th>
                {GERMAN_POLLUTANTS.map(([k, label]) => (
                  <th key={k} className={th}>
                    {label} Oct–Mar / Apr–Sep
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {d.comparison.map((c) => (
                <tr key={c.group} className="border-b border-neutral-100 last:border-0 dark:border-neutral-800">
                  <td className="px-2 py-1.5 capitalize">{c.group}</td>
                  <td className={td}>{c.stations}</td>
                  {GERMAN_POLLUTANTS.map(([k]) => (
                    <td key={k} className={td}>
                      {fmt(c[k].heating)} / {fmt(c[k].summer)} <span className="text-neutral-500">({ratioText(c[k].ratio)})</span>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Caveat>
        Winter air also tends to be stiller, with lower mixing heights, so the heating-season rise mixes emissions (wood stoves, heating) with weather;
        this page does not separate the two.
        Station groups are the Umweltbundesamt&apos;s own classification; not every station measures every pollutant.
      </Caveat>
      <Method
        items={[
          ["Period", `${d.basis.first ?? "–"} to ${d.basis.last ?? "–"}`],
          ["Seasons", d.basis.seasons],
          ["Groups", d.basis.stations],
          ["Values", `${UG}; the ratio is heating season divided by summer`],
        ]}
      />
    </>
  );
}

const TN_POLLUTANTS: ["so2" | "pm25" | "no2", string][] = [
  ["so2", "SO₂"],
  ["pm25", "PM2.5"],
  ["no2", "NO₂"],
];

function TamilNaduInsight({ d }: { d: TamilNaduLandUse }) {
  const [p, setP] = useState<"so2" | "pm25" | "no2">("so2");
  const headline = tamilNaduHeadline(d);
  const residential = d.groups.find((g) => g.use === "residential")?.stations ?? 0;
  return (
    <>
      {headline && <Headline>{headline}</Headline>}
      <div className="grid gap-3 sm:grid-cols-2">
        {d.groups.map((g) => (
          <Card key={g.use}>
            <h2 className="font-semibold capitalize">{g.use}</h2>
            <p className="text-xs text-neutral-500">
              {g.stations} station{g.stations === 1 ? "" : "s"} · median of station means
            </p>
            <dl className="mt-2 grid grid-cols-4 gap-2 text-center">
              {(["so2", "pm25", "pm10", "no2"] as const).map((k) => (
                <div key={k}>
                  <dt className="text-xs text-neutral-500">{{ so2: "SO₂", pm25: "PM2.5", pm10: "PM10", no2: "NO₂" }[k]}</dt>
                  <dd className="text-lg font-semibold tabular-nums">{fmt(g[k], 0)}</dd>
                </div>
              ))}
            </dl>
          </Card>
        ))}
      </div>
      {d.diurnal.length > 0 && (
        <Card className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold">Hour by hour</h2>
            <Toggle label="Pollutant" value={p} options={TN_POLLUTANTS} onChange={setP} />
          </div>
          <DiurnalChart diurnal={d.diurnal} pollutant={p} />
        </Card>
      )}
      <Card>
        <h2 className="font-semibold">Stations and why they are classified</h2>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-neutral-200 dark:border-neutral-800">
              <tr>
                <th className={th}>Station</th>
                <th className={th}>Class</th>
                <th className={th}>Basis</th>
                <th className={th}>SO₂</th>
                <th className={th}>PM2.5</th>
                <th className={th}>Days</th>
              </tr>
            </thead>
            <tbody>
              {d.stations.map((s) => (
                <tr key={s.id} className="border-b border-neutral-100 last:border-0 dark:border-neutral-800">
                  <td className="px-2 py-1.5">
                    <Link href={`/station/${s.id}`} className="hover:underline">
                      {s.name}
                    </Link>
                  </td>
                  <td className="px-2 py-1.5 capitalize">{s.use}</td>
                  <td className="px-2 py-1.5 text-xs text-neutral-600 dark:text-neutral-400">{s.basis}</td>
                  <td className={td}>{fmt(s.so2, 0)}</td>
                  <td className={td}>{fmt(s.pm25, 0)}</td>
                  <td className={td}>{s.days}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {d.basis.unclassified != null && d.basis.unclassified > 0 && (
          <p className="mt-2 text-xs text-neutral-500">
            {d.basis.unclassified} other Tamil Nadu stations have no published land-use class and are left out rather than guessed.
          </p>
        )}
      </Card>
      <Caveat>
        {residential <= 1 ? "Only one monitor is explicitly residential, so this is a comparison against a single site. " : ""}
        CPCB does not publish a land-use class per station; classes come only from station names that state it (an industrial estate, &ldquo;Res.
        Area&rdquo;) or a well-documented industrial belt, labelled as an AirAtlas classification.
      </Caveat>
      <Method items={[["Period", d.basis.period ?? "–"], ...(d.basis.rules ?? []).map((r): [string, string] => [`“${r.matches}”`, `${r.use}: ${r.basis}`])]} />
    </>
  );
}

const VIEWS = {
  festivals: (d: unknown) => <FestivalsInsight d={d as Festivals} />,
  "kerala-monsoon": (d: unknown) => <KeralaInsight d={d as KeralaMonsoon} />,
  "uae-dust": (d: unknown) => <UaeInsight d={d as UaeDust} />,
  "germany-seasons": (d: unknown) => <GermanyInsight d={d as GermanySeasons} />,
  "tamil-nadu-land-use": (d: unknown) => <TamilNaduInsight d={d as TamilNaduLandUse} />,
} satisfies Record<InsightSlug, (d: unknown) => ReactNode>;

export default function InsightView({ slug }: { slug: InsightSlug }) {
  const info = INSIGHTS.find((i) => i.slug === slug)!;
  const res = useApi<unknown>(`/insights/${slug}`);
  return (
    <article className="space-y-5">
      <header>
        <p className="text-sm">
          <Link href="/insights" className="text-sky-700 hover:underline dark:text-sky-400">
            ← Insights
          </Link>
        </p>
        <h1 className="mt-1 text-2xl font-bold sm:text-3xl">{info.title}</h1>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          {info.region} · computed from stored measurements, refreshed daily
        </p>
      </header>
      {res.error && <ErrorNote error={res.error} />}
      {res.data ? VIEWS[slug](res.data) : !res.error && <Skeleton className="h-96" />}
    </article>
  );
}
