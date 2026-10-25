"use client";

import Link from "next/link";
import { useApi } from "@/lib/api";
import { REGION_NAMES, SCALE_LABELS } from "@/lib/format";
import { FEATURED_LABEL } from "@/lib/regions";
import { REGION_CODES, type Compare, type Meta } from "@/lib/types";
import { useScale } from "@/lib/useScale";
import NearestStations from "./NearestStations";
import SearchBox from "./SearchBox";
import { AqiBadge, Card, ErrorNote, ScaleToggle, Skeleton } from "./ui";

export default function HomeView() {
  const [scale, setScale] = useScale(false);
  const meta = useApi<Meta>("/meta");
  const compare = useApi<Compare>(`/compare?scale=${scale}`, { keepPrevious: true });

  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">Air quality in four places, measured honestly</h1>
        <p className="max-w-2xl text-neutral-700 dark:text-neutral-300">
          Live and historical air quality for Tamil Nadu, Kerala, the UAE and Germany. Each region is shown on its own national index,
          and every view switches to a common scale so the regions can be compared fairly.
        </p>
        <div className="flex flex-wrap items-start gap-3">
          <SearchBox />
          <NearestStations />
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-xl font-semibold">Right now, on a common scale</h2>
          <ScaleToggle value={scale} options={["eu_eaqi", "who_2021_pm25"]} onChange={setScale} />
        </div>
        {compare.error && <ErrorNote error={compare.error} />}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {REGION_CODES.map((code) => {
            const r = compare.data?.now[code];
            const region = meta.data?.regions.find((x) => x.code === code);
            const f = r?.featured_area;
            return (
              <Link key={code} href={`/region/${code}?scale=${scale}`} className="group">
                <Card className="h-full transition-colors group-hover:border-neutral-400">
                  <h3 className="font-semibold">{REGION_NAMES[code]}</h3>
                  <p className="text-xs text-neutral-500">
                    {region
                      ? `${region.reference_stations} monitors · ${region.low_cost_stations} low-cost · ${region.modeled_points} model points`
                      : " "}
                  </p>
                  <div className="mt-3 min-h-8">
                    {!r ? (
                      <Skeleton className="h-8 w-40" />
                    ) : f?.value != null ? (
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm">{FEATURED_LABEL[code]}</span>
                        <AqiBadge category={f.category} size="sm" />
                        {f.basis === "modeled" && <span className="text-xs text-neutral-500">modeled</span>}
                      </div>
                    ) : (
                      <p className="text-sm text-neutral-500">{FEATURED_LABEL[code]}: data unavailable</p>
                    )}
                  </div>
                  {r && (
                    <p className="mt-2 text-xs text-neutral-500">
                      {r.stations_with_data} of {r.stations_total} stations have a current {SCALE_LABELS[scale]} value
                    </p>
                  )}
                </Card>
              </Link>
            );
          })}
        </div>
        <p className="text-sm">
          <Link href={`/compare?scale=${scale}`} className="font-medium text-sky-700 hover:underline dark:text-sky-400">
            Compare regions in detail →
          </Link>
          <span className="mx-2 text-neutral-400">·</span>
          <Link href="/insights" className="font-medium text-sky-700 hover:underline dark:text-sky-400">
            Insights: festivals, monsoon, dust, heating season →
          </Link>
        </p>
      </section>

      <section className="grid gap-3 md:grid-cols-3">
        <Card>
          <h3 className="font-semibold">Local standards</h3>
          <p className="mt-1 text-sm text-neutral-700 dark:text-neutral-300">
            India’s CPCB AQI, the UAE’s Emirati AQI and Germany’s UBA index, each computed from raw concentrations with the
            official breakpoints.
          </p>
        </Card>
        <Card>
          <h3 className="font-semibold">Common scales</h3>
          <p className="mt-1 text-sm text-neutral-700 dark:text-neutral-300">
            The European AQI (2025 bands) and PM2.5 against the WHO 2021 guideline make “good” mean the same thing everywhere.
          </p>
        </Card>
        <Card>
          <h3 className="font-semibold">No invented numbers</h3>
          <p className="mt-1 text-sm text-neutral-700 dark:text-neutral-300">
            Missing or stale data is shown as missing. Modeled estimates are always labelled as modeled.
          </p>
        </Card>
      </section>
    </div>
  );
}
