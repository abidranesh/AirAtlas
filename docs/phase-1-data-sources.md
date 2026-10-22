# Phase 1: Data source verification

Probed live on **2026-10-21** (≈17:00 UTC). Re-run with `python scripts/verify_sources.py`.

## Summary

| # | Source | Status | Key | Covers | Update freq | History |
|---|--------|--------|-----|--------|-------------|---------|
| 1 | CPCB via data.gov.in | ✅ works | free key | TN, Kerala | hourly | **none**: current snapshot only |
| 2 | UBA Air Data API **v4** | ✅ works (**v3 is down**) | none | Germany | hourly, ~2 h lag | back to 2016 |
| 3 | EEA Parquet downloads API | ✅ works | none | Germany (+EU) | daily batches (E2a, "up-to-date") | verified (E1a) to 2013+ |
| 4 | UAE official (NCM / EAD / Dubai) | ❌ no open API | — | UAE | — | — |
| 5 | OpenAQ v3 | ✅ works | free key | all four | hourly | yes (CPCB stations from 2016–2025) |
| 6 | Open-Meteo Air Quality | ✅ works | none | all four (modeled, ~11–40 km grid) | hourly | 2022-08 onward (CAMS) |
| 7 | Open-Meteo Weather + Archive | ✅ works | none | all four | hourly | ERA5, 1940 onward |
| 8 | NASA FIRMS | ✅ works (5,000 tx / 10 min) | free MAP_KEY | all four | ~3 h NRT | up to 5-day range/request |

## Findings that change the design

1. **UBA v3 is down.** `www.umweltbundesamt.de/api/air_data/v3/*` returns HTTP 503 with a maintenance page.
   The working endpoint is `https://luftdaten.umweltbundesamt.de/api/air-data/v4/`. v4 requires `date_from`/`date_to`
   and returns **times in CET/CEST, not UTC**, which the adapter must convert. The `airquality` endpoint returns both
   concentrations **and UBA's own index per pollutant**, so the Phase 2 UBA module can be tested against the agency's
   own numbers.
2. **CPCB has no history and reports rolling averages.** The data.gov.in resource is a live snapshot. The values in
   `min_value/max_value/avg_value` are CPCB's rolling averages (24 h for PM, 8 h for CO/O₃ per the NAQI method), not
   hourly concentrations. Plan: poll hourly to build our own history, store values with `averaging_period` metadata,
   and use OpenAQ, which archives the CPCB stations, for backfill and true hourly values.
3. **Indian coverage is thin and changes from hour to hour.** Only the stations that reported in the current hour
   appear. That is why discovery must run on every poll and stations need `last_seen_at`, not a fixed list.
4. **UAE has an official AQI but no open data.** NCM publishes the EAQI method (verified, see
   [aqi-standards/ae_eaqi.md](aqi-standards/ae_eaqi.md)) and runs about 31 stations, but I found no documented API
   or open-data download. Abu Dhabi's SDI station layer is licensed "for use by Abu Dhabi government entities only".
   **Decision:** measured UAE data comes only from OpenAQ (if UAE stations exist there), and everything else is
   Open-Meteo modeled data, labelled as modeled. AQICN (aqicn.org) redistributes EAD data, but it is a third-party
   aggregator with its own terms, so it is left out by default.
5. **Modeled values differ a lot from measured ones in India.** At the same hour, Open-Meteo gave Chennai PM2.5 =
   5.9 µg/m³ and Kochi = 15.3, while CPCB's Kannur station reported a 24 h average of 49. Modeled data fills gaps
   and is never presented as a measurement.
6. **EEA station codes match UBA codes** (`SPO.DE_DEBB021_PM2…` ↔ UBA `DEBB021`), so the two German sources can be
   deduplicated reliably.

## Station coverage per region

| Region | Measured (official) | Measured (OpenAQ) | Modeled |
|--------|--------------------|-------------------|---------|
| **Tamil Nadu** | 11 CPCB/TNPCB reporting now: Chennai ×7 (Royapuram, Arumbakkam, Kodungaiyur, Manali, Manali Village, Perungudi, Velachery), Gummidipoondi, Thoothukudi, Coimbatore, Madurai. 3 lack PM2.5. | 11 reference monitors active in 7 d. Adds **SIPCOT Perundurai** and the **US Consulate Chennai** (AirNow). Missing Madurai. 1 low-cost (Kudikadu, Cuddalore). **Union ≈ 14 stations** | Open-Meteo, 38 district centroids |
| **Kerala** | 4 reporting now: Thrissur, Thiruvananthapuram (Plammoodu), Kannur, Eloor. | 5 reference monitors (adds **Kariavattom**, TVM) + 1 low-cost (Malappuram). **Union ≈ 6.** Only Eloor (an industrial belt in Ernakulam) is near Kochi. | 14 district centroids |
| **UAE** | 0 (no open official API) | **12 low-cost AirGradient sensors, 0 reference monitors**: 10 in Dubai, 1 Ras Al Khaimah, 1 Ajman. **None in Abu Dhabi, Sharjah, Fujairah or UAQ.** | 7 emirates + ~18 grid points, including `dust` |
| **Germany** | UBA: **419 active**, 408 reporting this hour (urban 241 / suburban 89 / rural 89; background 273 / traffic 126 / industry 20). Average 3.4 pollutants per station. EEA: 348 PM2.5 series. | 386 EEA reference monitors active (fewer than UBA's 419, so UBA stays primary) + 209 low-cost AirGradient sensors | 16 Länder + ~44 city points |

Germany has enough rural and urban stations for the "city vs rural" insight. Tamil Nadu has industrial (Manali,
Gummidipoondi, SIDCO Kurichi) and residential (Velachery Res. Area) stations, so that insight is feasible.

## OpenAQ + FIRMS results (keys added 2026-10-21)

Counts below are from `iso=` filters for UAE/DE and from per-station name checks for TN/Kerala. A bounding box is not
enough there: the TN box also contains Bengaluru, Puducherry and Chittoor, and the Kerala box contains Coimbatore and
Mangaluru. **Ingestion must assign states by point-in-polygon against boundary GeoJSON, never by bbox.**

7. **UAE measured data is low-cost sensors only, and almost all of it is in Dubai.** This is the project's biggest
   coverage limitation. It will go in the README's "known limitations". On the map, Abu Dhabi, Sharjah, Fujairah and
   UAQ rely entirely on modeled data. AirGradient PM readings over-read in high humidity, so we apply a published
   humidity correction (documented in Phase 3) and give them a "low-cost sensor" badge, distinct from reference monitors.
8. **Low-cost sensors are a separate layer.** Germany's 209 AirGradient sensors (CC BY 4.0) are ingested with
   `station.kind = 'low_cost'` and shown on an optional layer. They are excluded from the regional AQI and from
   forecast training by default.
9. **Indian history comes from OpenAQ.** CPCB stations in OpenAQ go back to 2016–2021 (Velachery 2018, Manali 2016),
   so several years of Deepavali and Bhogi are available for the festival insight. Perundurai, Perungudi and
   SIDCO Kurichi only start in 2025-02.
10. **FIRMS in the UAE detects gas flares, not wildfires.** There were 35 detections in 24 h, at the time of year when
    there is nothing to burn. NRT data has no "static source" flag, so the anomaly engine will mask persistent hotspots
    (pixels detected on more than 50% of the last 90 days) before attributing a spike to "fire". There were 0
    detections in TN/Kerala now (monsoon); the crop-burning signal is expected Jan–Apr.
11. **Licences seen in OpenAQ:** EEA = ODC-BY, AirGradient = CC BY 4.0, Clarity = CC0. Licences are stored per
    station and listed on the attribution page.

Storage impact: the UAE estimate drops from 40 to 12 stations, but Germany adds up to 209 low-cost sensors. The net
measured total is ≈ 680 (vs 495), so the total becomes ≈ 602 MB (59% of Neon). `storage_budget.py` has been updated.

## Rate limits and call budget (checked 2026-10-21)

| Source | Limit | Our hourly use | Risk |
|--------|-------|----------------|------|
| OpenAQ v3 | 60/min, 2,000/h per key | ~80 calls (latest per location) | low; backfill needs throttling (≈1 call/1.1 s) |
| Open-Meteo (free, **non-commercial**) | 600/min, 5,000/h, **10,000/day**, 300k/month; each location counts as a call | 137 points × (AQ + weather) | **medium**: hourly polling = 6,576/day. **Mitigation:** poll every 3 h with `past_hours=3`, ≈2,200/day |
| UBA v4 | not published | 1 call (all stations) + meta | low; cached server-side |
| data.gov.in | per key; sample key caps at 10 rows | 2 calls | low; verify the cap with your own key |
| NASA FIRMS | 5,000 transactions / 10 min, ≤5 days per request | 4 bbox calls every 3 h | low |
| EEA | not published | daily backfill only | low |

## Platform free tiers (checked 2026-10-21)

| Service | Free limit | Card? | Risk and mitigation |
|---------|-----------|-------|---------------------|
| **Neon** (chosen) | 1 GB/project, 100 CU-h/month/project, 5 GB egress, scale-to-zero after 5 min | No | **Compute hours**: being awake all month at 0.25 CU = 180 CU-h, which exceeds 100. Hourly ingestion wakes it ~7 min/h ≈ 21 CU-h. The API must not keep it awake: CDN cache (`s-maxage` until the next ingestion) plus precomputed snapshots. When the limit is hit, Neon suspends compute; it does not bill. |
| Supabase | 500 MB DB, 5 GB egress, **pauses after 7 days of inactivity**, 2 projects | No | Budget below is ~100% of 500 MB, so it is rejected |
| GitHub Actions | Free for public repos; cron ≥5 min; **delays at the top of each hour**; **schedules are disabled after 60 days without repo activity** | No | Schedule at `:17`; weekly retraining commit/keepalive keeps the repo active |
| Vercel Hobby | 1M function invocations, 4 active-CPU-h, 100 GB transfer, 1M CDN requests per month; **non-commercial only**; over-limit = paused, not billed | No | Edge-cache API responses |

**Why Neon over Supabase:** we only need Postgres (no auth or storage). Neon gives twice the storage (1 GB vs
500 MB), and our budget is ~602 MB. Neon has no 7-day inactivity pause. The trade-off is the CU-hour cap, which
caching handles.

## Storage budget

From [`storage_budget.py`](storage_budget.py) (output in [`storage_budget.out.txt`](storage_budget.out.txt)):

- Hourly entities: 495 measured stations (with headroom) + 137 modeled points = **632** → **15,168 rows/day**.
- **Wide `readings` table** (one row per station-hour, one nullable column per pollutant): 90 days = **156 MB**,
  vs ~375 MB for a narrow one-row-per-pollutant table. New pollutants are rare, so a schema change is acceptable.
- Raw hourly data is kept for 90 days, using **monthly partitions dropped with `DROP TABLE`**. Bulk `DELETE` would
  leave dead tuples that still count toward the 1 GB.
- Daily aggregates are kept forever: ~40 MB/year. Backfill 3 years at launch (106 MB).
- Hourly festival windows kept forever (Deepavali, Bhogi, New Year's Eve; ±3 days, relevant region only): 51 MB over 5 years.
- **Total ≈ 602 MB (59% of Neon free)**, growing ~52 MB/year; the status page alerts at 80%.
- Germany: ingest all 419 stations (they fit). City-level aggregation is a view, not a storage saving.

## Sources

- UBA v4: <https://luftdaten.umweltbundesamt.de/api/air-data/v4/>; docs <https://luftqualitaet.api.bund.dev/>
- CPCB dataset: <https://www.data.gov.in/resource/real-time-air-quality-index-various-locations>
- EEA: <https://eeadmz1-downloads-api-appservice.azurewebsites.net/swagger/v1/swagger.json>
- UAE EAQI guideline (NCM, 2023): <https://airquality.ncm.gov.ae/resources/pdf/aqi-quickguide-en-2023.pdf>
- Abu Dhabi SDI station layer (gov-only licence): <https://arcgis.sdi.abudhabi.ae/agspublish/rest/services/OpenData/ADSDI_OpenData/MapServer/126/iteminfo>
- OpenAQ rate limits: <https://docs.openaq.org/using-the-api/rate-limits>
- Open-Meteo terms: <https://open-meteo.com/en/terms>
- NASA FIRMS area API: <https://firms.modaps.eosdis.nasa.gov/api/area/>
- Neon pricing: <https://neon.com/pricing>; Supabase pricing: <https://supabase.com/pricing>
- GitHub schedule event: <https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows>
- Vercel Hobby: <https://vercel.com/docs/plans/hobby>
