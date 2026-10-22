"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useApi } from "@/lib/api";
import { localTime, REGION_NAMES, SCALE_LABELS } from "@/lib/format";
import { FEATURED_LABEL } from "@/lib/regions";
import { REGION_CODES, type AreaSummary, type Compare, type Meta } from "@/lib/types";
import { useScale } from "@/lib/useScale";
import { AqiBadge, Card, ErrorNote, Legend, ScaleToggle, Skeleton } from "./ui";

const MonthlyChart = dynamic(() => import("./MonthlyChart"), { ssr: false, loading: () => <Skeleton className="h-72" /> });

function AreaList({ title, areas }: { title: string; areas: AreaSummary[] }) {
  return (
    <div>
      <h4 className="text-xs font-medium tracking-wide text-neutral-500 uppercase">{title}</h4>
      {areas.length === 0 ? (
        <p className="text-sm text-neutral-500">No current data</p>
      ) : (
        <ul className="mt-1 space-y-1 text-sm">
          {areas.map((a) => (
            <li key={a.area_id} className="flex items-center justify-between gap-2">
              <span className="truncate">
                {a.name}
                {a.basis === "modeled" && <span className="ml-1 text-xs text-neutral-500">(modeled)</span>}
              </span>
              <AqiBadge category={a.category} size="sm" />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function CompareView() {
  const [scale, setScale] = useScale(false);
  const meta = useApi<Meta>("/meta");
  const cmp = useApi<Compare>(`/compare?scale=${scale}`, { keepPrevious: true });
  const std = meta.data?.standards[scale];
  const featured = cmp.data?.monthly_pm25.featured_areas ?? [];

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold sm:text-3xl">Compare regions</h1>
          <p className="text-sm text-neutral-600 dark:text-neutral-400">
            Everything on one scale: {SCALE_LABELS[scale]}. Measured stations only; areas without them show modeled estimates, labelled.
            {cmp.data && ` Updated ${localTime(cmp.data.generated_at, "UTC")}.`}
          </p>
        </div>
        <ScaleToggle value={scale} options={["eu_eaqi", "who_2021_pm25"]} onChange={setScale} />
      </header>
      {cmp.error && <ErrorNote error={cmp.error} />}
      {std && <Legend standard={std} />}

      <div className={`grid gap-3 sm:grid-cols-2 lg:grid-cols-4 ${cmp.loading ? "opacity-70" : ""}`}>
        {REGION_CODES.map((code) => {
          const r = cmp.data?.now[code];
          return (
            <Card key={code} className="space-y-3">
              <div>
                <h2 className="font-semibold">
                  <Link href={`/region/${code}?scale=${scale}`} className="hover:underline">
                    {FEATURED_LABEL[code]}
                  </Link>
                </h2>
                <p className="text-xs text-neutral-500">{REGION_NAMES[code]}</p>
              </div>
              {!r ? (
                <Skeleton className="h-28" />
              ) : (
                <>
                  {r.featured_area?.value != null ? (
                    <AqiBadge category={r.featured_area.category} size="lg" />
                  ) : (
                    <p className="text-sm text-neutral-500">Data unavailable</p>
                  )}
                  <AreaList title="Cleanest areas now" areas={r.best_areas} />
                  <AreaList
                    title="Most polluted now"
                    areas={r.worst_areas.filter((w) => !r.best_areas.some((b) => b.area_id === w.area_id))}
                  />
                  <p className="text-xs text-neutral-500">
                    {r.stations_with_data} of {r.stations_total} measured stations reporting
                  </p>
                </>
              )}
            </Card>
          );
        })}
      </div>

      <Card>
        <h2 className="font-semibold">Monthly mean PM2.5, last 12 months</h2>
        <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-400">
          Average of measured stations’ daily means (days with at least 18 hours). WHO’s annual guideline is{" "}
          {cmp.data?.monthly_pm25.who_annual_guideline ?? 5} µg/m³.
        </p>
        {cmp.data ? <MonthlyChart rows={featured} guideline={cmp.data.monthly_pm25.who_annual_guideline} /> : <Skeleton className="h-72" />}
      </Card>
    </div>
  );
}
