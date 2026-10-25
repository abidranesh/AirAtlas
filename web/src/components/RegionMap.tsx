"use client";

import "leaflet/dist/leaflet.css";
import type * as Leaflet from "leaflet";
import { useEffect, useRef, useState } from "react";
import { ageText, KIND_LABELS, textOn } from "@/lib/format";
import { areaStyle, markerStyle } from "@/lib/mapStyle";
import type { AreaSummary, StationLatest } from "@/lib/types";

export interface BoundaryCollection {
  type: "FeatureCollection";
  features: { type: "Feature"; id: number; properties: { id: number; name: string; level: string }; geometry: GeoJSON.Geometry }[];
}

interface Props {
  bbox: number[][][];
  boundaries?: BoundaryCollection;
  areas: AreaSummary[];
  stations: StationLatest[];
  showModeled: boolean;
  /** PNG overlay covering bbox (interpolated PM2.5); undefined hides it. */
  heatmapUrl?: string;
  onOpenStation: (id: number) => void;
  className?: string;
}

function el(tag: string, text?: string, className?: string): HTMLElement {
  const e = document.createElement(tag);
  if (text) e.textContent = text; // textContent: names come from external data, never inject HTML
  if (className) e.className = className;
  return e;
}

function popupFor(s: StationLatest, onOpen: (id: number) => void): HTMLElement {
  const root = el("div", undefined, "min-w-44 space-y-1 text-sm");
  root.append(el("div", s.name, "font-semibold"), el("div", `${KIND_LABELS[s.kind]} · ${s.area ?? s.city ?? ""}`, "text-xs text-neutral-500"));
  const shown = s.aqi?.category ? s.aqi : null;
  if (shown?.category) {
    const b = el("span", `${shown.value ?? ""} ${shown.category.label}`.trim(), "inline-block rounded px-1.5 py-0.5 text-xs font-semibold");
    b.style.background = shown.category.color;
    b.style.color = textOn(shown.category.color);
    root.append(b);
  } else if (s.official) {
    const b = el("span", `${s.official.value} ${s.official.category.label} (official CPCB)`, "inline-block rounded px-1.5 py-0.5 text-xs font-semibold");
    b.style.background = s.official.category.color;
    b.style.color = textOn(s.official.category.color);
    root.append(b);
  } else {
    root.append(el("div", s.freshness === "unavailable" ? "Data unavailable" : "Not enough data for this standard", "text-xs"));
  }
  root.append(el("div", `Updated ${ageText(s.age_minutes)}`, "text-xs text-neutral-500"));
  const link = el("button", "Open station →", "text-xs font-medium text-sky-700 underline") as HTMLButtonElement;
  link.type = "button";
  link.onclick = () => onOpen(s.id);
  root.append(link);
  return root;
}

export default function RegionMap({ bbox, boundaries, areas, stations, showModeled, heatmapUrl, onOpenStation, className }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<Leaflet.Map | null>(null);
  const lib = useRef<typeof Leaflet | null>(null);
  const layers = useRef<{ areas?: Leaflet.GeoJSON; stations?: Leaflet.LayerGroup; heat?: Leaflet.ImageOverlay }>({});
  const [ready, setReady] = useState(false);

  // Create the map once. Leaflet touches `window`, so it is imported only in the browser.
  useEffect(() => {
    let cancelled = false;
    import("leaflet").then((mod) => {
      const L = mod.default;
      if (cancelled || !container.current || map.current) return;
      lib.current = L;
      const m = L.map(container.current, { preferCanvas: true, zoomSnap: 0.25, attributionControl: true });
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 18,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      }).addTo(m);
      m.fitBounds(L.latLngBounds(bbox[0].map(([lon, lat]) => [lat, lon] as [number, number])), { padding: [8, 8] });
      // Heatmap sits above the tiles but below area outlines and markers (overlayPane is z-index 400).
      m.createPane("heat").style.zIndex = "350";
      m.getPane("heat")!.style.pointerEvents = "none";
      map.current = m;
      setReady(true);
    });
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
    };
    // bbox is fixed per region; the parent remounts this component when the region changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Redraw data layers whenever data or filters change.
  useEffect(() => {
    const L = lib.current;
    const m = map.current;
    if (!ready || !L || !m) return;
    layers.current.areas?.remove();
    layers.current.stations?.remove();

    if (boundaries) {
      const byId = new Map(areas.map((a) => [a.area_id, a]));
      layers.current.areas = L.geoJSON(boundaries as GeoJSON.FeatureCollection, {
        style: (f) => areaStyle(byId.get(f?.properties.id), Boolean(heatmapUrl)),
        onEachFeature: (f, layer) => {
          const a = byId.get(f.properties.id);
          const tip = el("div");
          tip.append(el("strong", f.properties.name));
          tip.append(
            el(
              "div",
              a?.value != null ? `${a.value} · ${a.category?.label}${a.basis === "modeled" ? " (modeled estimate)" : ""}` : "No data",
            ),
          );
          layer.bindTooltip(tip, { sticky: true });
        },
      }).addTo(m);
    }

    const group = L.layerGroup();
    // Measured stations on top of modeled points.
    const order = { modeled: 0, low_cost: 1, reference: 2 } as const;
    [...stations]
      .filter((s) => showModeled || s.kind !== "modeled")
      .sort((a, b) => order[a.kind] - order[b.kind])
      .forEach((s) => {
        const marker = L.circleMarker([s.lat, s.lon], markerStyle(s));
        marker.bindPopup(() => popupFor(s, onOpenStation));
        marker.bindTooltip(s.name, { direction: "top", offset: [0, -6] });
        group.addLayer(marker);
      });
    layers.current.stations = group.addTo(m);
  }, [ready, boundaries, areas, stations, showModeled, heatmapUrl, onOpenStation]);

  // Interpolated overlay: the API renders it for exactly the region's bbox.
  useEffect(() => {
    const L = lib.current;
    const m = map.current;
    if (!ready || !L || !m) return;
    layers.current.heat?.remove();
    layers.current.heat = undefined;
    if (heatmapUrl) {
      const bounds = L.latLngBounds(bbox[0].map(([lon, lat]) => [lat, lon] as [number, number]));
      layers.current.heat = L.imageOverlay(heatmapUrl, bounds, { pane: "heat", interactive: false, alt: "Interpolated PM2.5 heatmap" }).addTo(m);
    }
    // bbox is fixed per region (component is keyed by region)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, heatmapUrl]);

  return (
    <div
      ref={container}
      role="region"
      aria-label="Map of stations and areas coloured by air quality"
      className={`z-0 overflow-hidden rounded-xl border border-neutral-200 dark:border-neutral-800 ${className ?? ""}`}
    />
  );
}
