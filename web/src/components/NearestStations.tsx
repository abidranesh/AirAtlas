"use client";

import Link from "next/link";
import { useState } from "react";
import { getJSON } from "@/lib/api";
import { ageText, fmt } from "@/lib/format";
import type { NearestStation } from "@/lib/types";
import { AqiBadge } from "./ui";

type State = { status: "idle" | "locating" | "loading" } | { status: "error"; message: string } | { status: "done"; stations: NearestStation[] };

export default function NearestStations() {
  const [state, setState] = useState<State>({ status: "idle" });

  function locate() {
    if (!("geolocation" in navigator)) {
      setState({ status: "error", message: "Your browser does not support location." });
      return;
    }
    setState({ status: "locating" });
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        setState({ status: "loading" });
        // ~1 km precision is enough to find a station and lets nearby visitors share cached answers.
        const lat = pos.coords.latitude.toFixed(2);
        const lon = pos.coords.longitude.toFixed(2);
        try {
          const { stations } = await getJSON<{ stations: NearestStation[] }>(`/nearest?lat=${lat}&lon=${lon}&limit=3`);
          setState({ status: "done", stations });
        } catch (e) {
          setState({ status: "error", message: (e as Error).message });
        }
      },
      (err) => setState({ status: "error", message: err.code === err.PERMISSION_DENIED ? "Location permission was denied." : "Could not get your location." }),
      { maximumAge: 600_000, timeout: 15_000 },
    );
  }

  return (
    <div className="space-y-2">
      <button
        onClick={locate}
        disabled={state.status === "locating" || state.status === "loading"}
        className="rounded-lg border border-neutral-300 px-3 py-2 text-sm font-medium hover:bg-neutral-100 disabled:opacity-60 dark:border-neutral-700 dark:hover:bg-neutral-800"
      >
        {state.status === "locating" ? "Locating…" : state.status === "loading" ? "Finding stations…" : "Use my location"}
      </button>
      {state.status === "error" && <p className="text-sm text-red-700 dark:text-red-300">{state.message}</p>}
      {state.status === "done" && (
        <ul className="space-y-1 text-sm">
          {state.stations.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-2">
              <Link href={`/station/${s.id}`} className="font-medium hover:underline">
                {s.name}
              </Link>
              <span className="text-xs text-neutral-500">{fmt(s.distance_km)} km</span>
              {s.aqi?.category ? (
                <AqiBadge category={s.aqi.category} value={s.aqi.standard === "in_cpcb_naqi" || s.aqi.standard === "ae_eaqi" ? s.aqi.value : undefined} size="sm" />
              ) : (
                <span className="text-xs text-neutral-500">{s.freshness === "unavailable" ? "data unavailable" : ageText(s.age_minutes)}</span>
              )}
            </li>
          ))}
          {state.stations.length > 0 && state.stations[0].distance_km > 100 && (
            <li className="text-xs text-neutral-500">AirAtlas covers Tamil Nadu, Kerala, the UAE and Germany; the nearest station is far away.</li>
          )}
        </ul>
      )}
    </div>
  );
}
