# Phase 5: Frontend

Next.js 16 (App Router, Cache Components, Partial Prefetching) + TypeScript + Tailwind v4, Leaflet with
OpenStreetMap tiles, Recharts. Deployed with the API as one Vercel project.

## Pages

| Route | What it shows |
|---|---|
| `/` | Region cards on a common scale (featured area now, station counts), search, "use my location" |
| `/region/[code]` | Map: areas coloured by AQI (dashed = modeled estimate), monitors / low-cost sensors / modeled points with distinct markers; legend; area ranking; station list; per-region coverage caveats; local / European AQI / WHO toggle |
| `/station/[id]` | The same air on all three scales side by side, health advice, CPCB's official index (India), latest hour with sub-indices, trends (24 h / 7 d / 30 d hourly, 1 y daily) with hourly AQI bars |
| `/compare` | Chennai vs Kochi vs Dubai vs Berlin on one scale, cleanest and most polluted areas now, monthly PM2.5 vs the WHO annual guideline |

## Decisions

- **Static shells, browser-side data.** Every route prerenders. The build reports `/`, `/compare` and the
  four region pages as static, and station pages as partial prerenders. Data is fetched in the browser from
  same-origin `/api/v1`, whose responses are CDN-cached until the next ingestion (Phase 4). The scale toggle
  is instant, there is no server-to-API hop to configure, and the HTML is served straight from the CDN.
- **The scale lives in the URL** (`?scale=eu_eaqi`), so any view can be shared; the last common scale is
  remembered with `useSyncExternalStore` (no hydration mismatch).
- **Leaflet over MapLibre**: ~40 KB vs ~200 KB gzipped, for the Lighthouse mobile target. It is
  loaded only on region pages (`next/dynamic`, `ssr: false`), with a canvas renderer for Germany's 435
  markers. Recharts is likewise loaded only when a chart renders.
- **Popups are built with DOM nodes and `textContent`**, never HTML strings, because station names come
  from external sources.
- **Level scales never show a number.** UBA's "3" or the EEA's "3" would read like an index value, so
  only the 0–500 indices (CPCB, UAE) show numbers.
- **Honest states everywhere:** "Data unavailable" (older than 24 h), "Stale · 6 h ago", "Not enough
  hours yet" (averaging window incomplete), "official" for CPCB's published index, "(modeled)" for estimates.
- **Times are in the region's local time** (IST, GST, CET/CEST with daylight saving); stored data is UTC.

## Verified in the browser (2026-10-22, against live data)

- Germany: 419 monitors and 16 modeled points drawn, the latest hour shown as "06:00 CEST" (04:00 UTC),
  and the toggle switching legend, colours and URL.
- Kerala: the four CPCB stations show the official index (e.g. Kannur 70, Satisfactory, "CPCB 22:00
  IST") while AirAtlas's own computation correctly says "Data unavailable" during OpenAQ's India outage.
- Station "Berlin Frankfurter Allee": UBA **Good**, European AQI **Moderate** (NO₂ 26 µg/m³), WHO
  **interim target 4, 1.4× the guideline**. That is the cross-standard difference this project exists to show.
- At 375 px (mobile) no page scrolls horizontally, and there are no console errors on any page.
- `next build` passes the Cache Components prerender validation.

Not yet measured: a Lighthouse score (planned for Phase 10 against the deployed site).

## Running locally

```bash
python api/dev_server.py                         # API on :8000 (reads ../.env)
cd web && echo API_ORIGIN=http://127.0.0.1:8000 > .env.local && npm install && npm run dev
npm test && npm run typecheck && npm run lint    # in web/
```

## Deploying

One Vercel project serves both apps with **Vercel Services** (root `vercel.json`): `/api/*` goes to the
FastAPI service and everything else to Next.js, on one domain in `fra1` next to Neon.

1. Sign in at <https://vercel.com/signup> with GitHub (Hobby plan: free, no card).
2. **Add New → Project** and import `abidranesh/AirAtlas`. Leave **Root Directory** as the repository root,
   so Vercel reads `vercel.json` and builds both services.
3. Add the environment variable `DATABASE_URL` (the pooled Neon string).
4. Deploy, then open `/`, `/region/germany` and `/api/docs`.

Vercel Services is in beta. If the build rejects the services config, the fallback is two projects: one with
Root Directory `api`, and one with Root Directory `web` plus `API_ORIGIN=https://<api-project>.vercel.app`.
The existing rewrite in `web/next.config.ts` then proxies `/api` to it.
