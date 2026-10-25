"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { useApi } from "@/lib/api";
import { ageText, localTime, POLLUTANTS } from "@/lib/format";
import { REGION_NOTES } from "@/lib/regions";
import type { FireCollection, Meta, RegionAnomalies, RegionCode, RegionLatest, StationLatest } from "@/lib/types";
import { useScale } from "@/lib/useScale";
import { EpisodeItem } from "./AnomalyList";
import type { BoundaryCollection } from "./RegionMap";
import { AqiBadge, Card, ErrorNote, FreshnessBadge, KindBadge, Legend, ScaleToggle, Skeleton } from "./ui";

const AnomalyTimeline = dynamic(() => import("./Anomalies").then((m) => m.AnomalyTimeline), {
  ssr: false,
  loading: () => <Skeleton className="h-44" />,
});
const RegionMap = dynamic(() => import("./RegionMap"), {
  ssr: false,
  loading: () => <Skeleton className="h-[55vh] min-h-80" />,
});

function sortKey(s: StationLatest): number {
  return s.aqi?.value ?? (s.official ? s.official.value : -1);
}

export default function RegionView({ code }: { code: RegionCode }) {
  const [scale, setScale] = useScale(true);
  const router = useRouter();
  const meta = useApi<Meta>("/meta");
  const latest = useApi<RegionLatest>(`/regions/${code}/latest?scale=${scale}`, { keepPrevious: true });
  const boundaries = useApi<BoundaryCollection>(`/regions/${code}/boundaries`);
  const [showModeled, setShowModeled] = useState(true);
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [showFires, setShowFires] = useState(false);
  const fires = useApi<FireCollection>(showFires ? `/regions/${code}/fires?hours=48` : null);
  const anomalies = useApi<RegionAnomalies>(`/regions/${code}/anomalies?days=30`);

  const data = latest.data;
  const region = meta.data?.regions.find((r) => r.code === code);
  const standard = data && meta.data ? meta.data.standards[data.standard] : undefined;
  const tz = region?.timezone ?? "UTC";
  // Level scales (UBA, European AQI, WHO) have no numeric index; showing "3" would read like an AQI value.
  const isIndex = standard?.scale.type === "index";

  const openStation = useCallback(
    (id: number) => router.push(`/station/${id}${scale !== "local" ? `?scale=${scale}` : ""}`),
    [router, scale],
  );

  const measured = useMemo(
    () => (data?.stations ?? []).filter((s) => s.kind !== "modeled").sort((a, b) => sortKey(b) - sortKey(a)),
    [data],
  );
  const counts = useMemo(() => {
    const c = { fresh: 0, stale: 0, unavailable: 0 };
    measured.forEach((s) => c[s.freshness]++);
    return c;
  }, [measured]);
  const newest = measured.map((s) => s.latest_ts).filter(Boolean).sort().at(-1) as string | undefined;
  const areas = useMemo(
    () => [...(data?.areas ?? [])].sort((a, b) => (b.value ?? -1) - (a.value ?? -1)),
    [data],
  );

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold sm:text-3xl">{region?.name ?? data?.region.name ?? "…"}</h1>
          <p className="text-sm text-neutral-600 dark:text-neutral-400">
            {newest ? `Latest measurement ${localTime(newest, tz)}` : "Waiting for measurements"}
            {measured.length > 0 && ` · ${counts.fresh} current, ${counts.stale} stale, ${counts.unavailable} unavailable`}
          </p>
        </div>
        <ScaleToggle value={scale} options={["local", "eu_eaqi", "who_2021_pm25"]} onChange={setScale} />
      </header>

      {latest.error && <ErrorNote error={latest.error} />}

      <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
        <div className="space-y-2">
          {region ? (
            <div className={latest.loading ? "opacity-70 transition-opacity" : ""}>
              <RegionMap
                key={code}
                bbox={region.bbox.coordinates}
                boundaries={boundaries.data}
                areas={data?.areas ?? []}
                stations={data?.stations ?? []}
                showModeled={showModeled}
                heatmapUrl={showHeatmap ? `/api/v1/regions/${code}/heatmap.png?scale=${scale}` : undefined}
                fires={showFires ? fires.data : undefined}
                onOpenStation={openStation}
                className="h-[55vh] min-h-80"
              />
            </div>
          ) : (
            <Skeleton className="h-[55vh] min-h-80" />
          )}
          {showHeatmap && (
            <p className="text-xs text-neutral-600 dark:text-neutral-400">
              Heatmap: PM2.5 interpolated between stations (inverse distance weighting; monitors weigh more than model points),
              averaged the way {standard?.short_name ?? "this standard"} does, coloured on its PM2.5 bands. An estimate, not a
              measurement; blank where no station is within range.
            </p>
          )}
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-neutral-600 dark:text-neutral-400">
            <span className="flex flex-wrap items-center gap-3">
              <span className="inline-flex items-center gap-1"><span className="inline-block size-3 rounded-full border border-neutral-900 bg-neutral-400" /> Monitor</span>
              <span className="inline-flex items-center gap-1"><span className="inline-block size-3 rounded-full border border-dashed border-neutral-900 bg-neutral-400" /> Low-cost sensor</span>
              <span className="inline-flex items-center gap-1"><span className="inline-block size-3 rounded-full border-2 border-neutral-500" /> Modeled point</span>
              <span>Dashed areas = modeled estimate</span>
            </span>
            <span className="flex flex-wrap gap-3">
              <label className="inline-flex items-center gap-1.5">
                <input type="checkbox" checked={showHeatmap} onChange={(e) => setShowHeatmap(e.target.checked)} />
                Heatmap
              </label>
              <label className="inline-flex items-center gap-1.5">
                <input type="checkbox" checked={showFires} onChange={(e) => setShowFires(e.target.checked)} />
                Fires (48 h)
                {showFires && fires.data && <span className="text-neutral-500">· {fires.data.features.length}</span>}
              </label>
              <label className="inline-flex items-center gap-1.5">
                <input type="checkbox" checked={showModeled} onChange={(e) => setShowModeled(e.target.checked)} />
                Show modeled points
              </label>
            </span>
          </div>
        </div>

        <aside className="space-y-4">
          <Card>{standard ? <Legend standard={standard} /> : <Skeleton className="h-16" />}</Card>
          <Card>
            <h2 className="mb-2 font-semibold">Areas</h2>
            {!data ? (
              <Skeleton className="h-40" />
            ) : (
              <ol className="max-h-80 space-y-1 overflow-y-auto pr-1 text-sm">
                {areas.map((a) => (
                  <li key={a.area_id} className="flex items-center justify-between gap-2">
                    <span className="truncate">
                      {a.name}
                      {a.basis === "modeled" && <span className="ml-1 text-xs text-neutral-500">(modeled)</span>}
                    </span>
                    {a.value == null ? (
                      <span className="text-xs text-neutral-500">no data</span>
                    ) : (
                      <AqiBadge category={a.category} value={isIndex ? a.value : undefined} size="sm" showLabel={!isIndex} />
                    )}
                  </li>
                ))}
              </ol>
            )}
          </Card>
          <Card className="text-sm text-neutral-700 dark:text-neutral-300">
            <h2 className="mb-1 font-semibold">About this data</h2>
            <ul className="list-disc space-y-1 pl-4">
              {REGION_NOTES[code].map((n) => (
                <li key={n}>{n}</li>
              ))}
              <li>Modeled values are CAMS estimates via Open-Meteo, not measurements.</li>
            </ul>
          </Card>
        </aside>
      </div>

      <Card>
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-semibold">Pollution spikes, last 30 days</h2>
          {anomalies.data && <span className="text-xs text-neutral-500">{anomalies.data.episodes.length} episodes</span>}
        </div>
        <p className="mb-3 text-xs text-neutral-600 dark:text-neutral-400">
          Hours far above the same hour on the previous 7 days (robust z ≥ 4 and 1.5× usual). Causes are hints from fires, wind,
          dust, rain, festivals and neighbouring stations, not proof.
        </p>
        {anomalies.error ? (
          <ErrorNote error={anomalies.error} />
        ) : !anomalies.data ? (
          <Skeleton className="h-44" />
        ) : (
          <>
            <AnomalyTimeline data={anomalies.data} />
            <ul className="mt-2 divide-y divide-neutral-200 dark:divide-neutral-800">
              {anomalies.data.episodes.slice(0, 8).map((ep) => (
                <EpisodeItem key={ep.id} ep={ep} tz={tz} />
              ))}
            </ul>
          </>
        )}
      </Card>

      <Card>
        <h2 className="mb-3 font-semibold">Monitors and sensors ({measured.length})</h2>
        {!data ? (
          <Skeleton className="h-48" />
        ) : (
          <ul className="divide-y divide-neutral-200 dark:divide-neutral-800">
            {measured.map((s) => (
              <li key={s.id} className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 py-2 sm:grid-cols-[1fr_9rem_auto_7rem]">
                <div className="min-w-0">
                  <Link href={`/station/${s.id}${scale !== "local" ? `?scale=${scale}` : ""}`} className="block truncate font-medium hover:underline">
                    {s.name}
                  </Link>
                  <div className="flex flex-wrap items-center gap-1.5 text-xs text-neutral-500">
                    <KindBadge kind={s.kind} />
                    <span>{s.area ?? s.city}</span>
                  </div>
                </div>
                <div className="hidden text-xs text-neutral-600 sm:block dark:text-neutral-400">
                  {s.aqi?.dominant.length ? `Driven by ${s.aqi.dominant.map((p) => POLLUTANTS[p]?.label ?? p).join(", ")}` : ""}
                </div>
                <div className="justify-self-end">
                  {s.aqi?.category ? (
                    <AqiBadge category={s.aqi.category} value={isIndex ? s.aqi.value : undefined} size="sm" />
                  ) : s.official ? (
                    <span title={s.official.note}>
                      <AqiBadge category={s.official.category} value={s.official.value} size="sm" />
                      <span className="ml-1 text-xs text-neutral-500">official</span>
                    </span>
                  ) : (
                    <span className="text-xs text-neutral-500">
                      {s.freshness === "unavailable" ? "Data unavailable" : "Not enough hours yet"}
                    </span>
                  )}
                </div>
                <div className="col-span-2 sm:col-span-1 sm:justify-self-end">
                  {!s.aqi?.category && s.official ? (
                    <span className="text-xs text-neutral-500">CPCB {localTime(s.official.reported_at, tz, false)}</span>
                  ) : (
                    <FreshnessBadge freshness={s.freshness} age={ageText(s.age_minutes)} />
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
