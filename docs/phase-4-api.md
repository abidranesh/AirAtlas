# Phase 4: Read API

FastAPI on Vercel's Python runtime (Hobby plan, region `fra1` next to Neon Frankfurt). Interactive
OpenAPI docs are served at `/api/docs`.

## Why FastAPI rather than Next.js API routes

The AQI engine is Python, with 115 tests. A TypeScript API would need a second implementation of
every standard's rules (CPCB's continuous bands, the UAE's O₃/SO₂ switching, rounding and truncation
conventions), and two implementations drift apart. With FastAPI the engine is used as-is: the API is a thin
read layer that loads raw concentrations and runs the same code the tests cover. Vercel runs FastAPI
natively on the free plan, and its "Services" feature puts the Phase 5 Next.js frontend on the same domain.

The engine has no dependencies, so the Vercel build step (`api/vendor_engine.py`) copies it next to
`app.py`. CI runs that same step.

## Endpoints

| Endpoint | Purpose | Cache (CDN) |
|---|---|---|
| `GET /api/v1/meta` | Regions, every standard's categories/colours/health advice, source attribution | 1 day |
| `GET /api/v1/regions/{region}/latest?scale=local\|eu_eaqi\|who_2021_pm25` | Every station (measured, low-cost, modeled) with freshness, AQI and latest concentrations, plus a value per admin area for the choropleth; India also returns CPCB's official index | until next ingestion |
| `GET /api/v1/regions/{region}/boundaries` | Simplified admin-area GeoJSON | 7 days |
| `GET /api/v1/regions/{region}/heatmap.png?scale=` | Interpolated PM2.5 overlay ([Phase 6](phase-6-heatmap.md)) | until next ingestion |
| `GET /api/v1/regions/{region}/anomalies?days=` / `GET /api/v1/stations/{id}/anomalies` | Spike episodes with cause hints ([Phase 7](phase-7-anomalies.md)) | until next ingestion |
| `GET /api/v1/regions/{region}/fires?hours=` | FIRMS detections (GeoJSON), persistent hotspots flagged | until next ingestion |
| `GET /api/v1/stations/{id}` | AQI on the local standard and both common scales, per-pollutant sub-indices, health advice, sources and licences | until next ingestion |
| `GET /api/v1/stations/{id}/series?range=24h\|7d\|30d\|1y` | Hourly concentrations (≤ 30 d), daily (1 y), hourly AQI for 24 h / 7 d | until next ingestion |
| `GET /api/v1/nearest?lat&lon` | Nearest measured stations (PostGIS KNN) with current AQI | until next ingestion |
| `GET /api/v1/search?q=` | Stations and areas, accent-insensitive (`gorlitz` → Görlitz) | 1 day |
| `GET /api/v1/compare?scale=eu_eaqi\|who_2021_pm25` | Featured areas (Chennai, Ernakulam/Kochi, Dubai, Berlin), best/worst areas now, monthly PM2.5 vs WHO | until next ingestion |
| `GET /api/v1/status` | Last success / failures (24 h) per region and source, data freshness, storage vs the 1 GB limit | 60 s |
| `GET /api/v1/health` | Liveness + DB round trip | none |

## Caching against Neon's compute limit

Neon's free tier allows 100 compute-hours per month, and a database kept awake all month would use
about 180. The CDN therefore absorbs reads.

- Live responses carry `s-maxage` = seconds until the next **:25 past the hour**, which is when the hourly
  ingestion (cron at :17) has finished. The CDN serves a response until new data exists, then one request
  revalidates while others get the stale copy (`stale-while-revalidate=600`).
- So the database wakes about once per hour per distinct URL, independent of visitor numbers.
- The connection pool has `min_size=0` and `max_idle=60`, so an idle function holds no connection and
  Neon can scale to zero.
- `/nearest` rounds coordinates to 0.01° (~1 km) so nearby visitors share cache entries.

## Honesty rules (enforced in `evaluate.py`, tested)

- **Freshness:** a station is `fresh` while its newest hour is under 5 h old for monitors (UBA publishes
  about 3–4 h late) or 7 h for models; `stale` after that (shown with its age); after 24 h it is
  `unavailable`, with `aqi: null` and no concentrations. A 30-hour-old value is never shown as current.
- **Insufficient data** is reported, not filled in. CPCB needs 24-hour averages with ≥ 16 valid hours, so a
  station with 7 hours of data returns `status: insufficient_data` and `value: null`.
- **Area colours** use the median of the area's measured stations (one roadside monitor should not paint a
  district red). Only areas without measured data use their modeled point, and they are labelled
  `basis: "modeled"`.
- **CPCB's official index** is returned separately (`official`) and labelled "as published", never mixed with
  AirAtlas's own computation.

## Measured on live data (2026-10-22, before the backfill)

| Call | Time (cold) | Size |
|---|---|---|
| Germany latest (435 stations) | 1.0–3.3 s | 219 KB (~40 KB gzipped) |
| Compare (all regions) | 3.3 s | 4 KB |
| Status | 1.0 s | 4 KB |
| Search | 0.2 s | <1 KB |

The slow calls run at most once per hour per URL; every other request is a CDN hit.

## Deploying

The API deploys together with the web app as one Vercel project (Vercel Services); see
[phase-5-frontend.md](phase-5-frontend.md#deploying).
