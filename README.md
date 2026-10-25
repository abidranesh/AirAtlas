# AirAtlas

Real-time and historical air quality for **Tamil Nadu, Kerala, the UAE and Germany**. Each region is shown on its
own national AQI standard, with a common scale for fair cross-country comparison, plus 24–48 h forecasts and
explained pollution spikes. Runs entirely on free tiers.

> Status: **Phase 8 complete**, live at https://airatlas-omega.vercel.app. [1: sources and storage budget](docs/phase-1-data-sources.md) · [2: AQI engine](aqi-engine/README.md) ([standards](docs/aqi-standards/README.md)) · [3: database and ingestion](docs/phase-3-ingestion.md) · [4: read API](docs/phase-4-api.md) · [5: frontend](docs/phase-5-frontend.md) · [6: IDW heatmap](docs/phase-6-heatmap.md) · [7: anomalies and cause hints](docs/phase-7-anomalies.md) · [8: insight pages](docs/phase-8-insights.md)

## Repository layout

```
api/          Python: FastAPI read API (Vercel), AQI computed at read time with aqi-engine
ingestion/    Python: one adapter per data source behind a common interface; GitHub Actions cron per region
aqi-engine/   Python: pluggable AQI standards (CPCB NAQI, UBA, EEA EAQI, UAE EAQI, WHO 2021) + unit conversion
ml/           Python: anomaly detection with cause hints (fires, dust, wind, festivals); forecasts in Phase 9
web/          Next.js 16 + TypeScript + Tailwind, Leaflet maps, Recharts (Vercel, same project as api/)
docs/         Source verification, AQI breakpoint tables with sources, storage budget, ADRs
scripts/      One-off tools (source verification)
```

## Quick start

```bash
cp .env.example .env              # add your free keys (see .env.example for sign-up links)
python scripts/verify_sources.py  # probes every source, prints coverage per region
python docs/storage_budget.py     # reproducible storage math
pip install -e aqi-engine -e "ingestion[dev]" -e "api[dev]" uvicorn
python -m airatlas_ingest migrate && python -m airatlas_ingest boundaries
python -m airatlas_ingest hourly --region germany
(cd api && uvicorn app:app --reload)            # http://localhost:8000/api/docs
for d in aqi-engine ingestion api; do (cd $d && python -m pytest -q); done   # set TEST_DATABASE_URL for DB tests
```

## Adding a region

1. **Config**: add a `Region` to `ingestion/src/airatlas_ingest/config.py` with its bbox, IANA timezone,
   geoBoundaries layer, and the sources that cover it. Add a row to `regions` in a new migration.
2. **Data adapter** (only if no existing source covers it): add `ingestion/src/airatlas_ingest/adapters/<source>.py`
   with pure `parse_*` functions that return validated `StationIn` / `Reading` models, record real
   responses as fixtures in `ingestion/tests/fixtures/`, and add the source to `sources` (with its priority
   and licence) in a migration.
3. **AQI standard** (only if the country has its own): add a JSON table under `aqi-engine/src/airatlas_aqi/tables/`,
   register it in `registry.py`, and test it against the official worked examples (see `aqi-engine/README.md`).
4. Load boundaries (`python -m airatlas_ingest boundaries --region <code>`), add the region to the
   workflow matrices in `.github/workflows/`, and run the backfill workflow once.

Nothing else changes: storage, retention, aggregation, the API and the UI are region-agnostic.

## Data sources and attribution

| Source | Licence / terms |
|--------|-----------------|
| CPCB via data.gov.in | Government Open Data License – India |
| Umweltbundesamt (UBA) | "Source: Umweltbundesamt" attribution required (dl-de/by-2-0) |
| European Environment Agency | CC BY 4.0 |
| OpenAQ | Per-provider licences, returned with each location |
| Open-Meteo | CC BY 4.0; free API is non-commercial |
| NASA FIRMS | NASA open data; cite LANCE FIRMS |

The full README (architecture diagram, AQI comparison table, methodology, trade-offs, limitations) is written in Phase 10.
