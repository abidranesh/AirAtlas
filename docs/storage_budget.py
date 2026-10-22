"""Storage budget for AirAtlas on the Neon free tier (1 GB per project).

Run:  python docs/storage_budget.py
Every input below is either measured (Phase 1 probes, 2026-10-21) or an
explicit, conservative assumption. Change the numbers and re-run.
"""

from dataclasses import dataclass

NEON_FREE_BYTES = 1 * 1024**3  # 1 GB per project (neon.com/pricing, checked 2026-10-21)

# --- Entities that produce one hourly row ------------------------------------
# Measured station counts (live, 2026-10-21) with headroom for stations that
# were offline at probe time.
MEASURED_STATIONS = {
    "germany": 420,      # UBA v4: 419 active (OpenAQ low-cost sensors not polled; see config.py)
    "tamil_nadu": 25,    # CPCB + OpenAQ union ~14; headroom for offline ones
    "kerala": 10,        # CPCB + OpenAQ union ~6
    "uae": 15,           # OpenAQ: 12 AirGradient low-cost, 0 reference monitors
}
# Modeled points from Open-Meteo (district/emirate/state centroids + gap fill).
MODELED_POINTS = {"germany": 16, "tamil_nadu": 38, "kerala": 14, "uae": 18}  # loaded 2026-10-22: 1 per admin area + UAE grid

# --- Postgres row-size estimates (bytes, including the PK btree entry) -------
# readings is WIDE: one row per (station, hour) with one nullable REAL column
# per pollutant. 23-24 B tuple header + 4 B item pointer + int4 station_id +
# timestamptz + 8 x real + source/flags ~= 76 B heap, ~32 B in the PK index,
# plus ~10% page slack.
BYTES_READING_WIDE = 120
# A narrow (station, pollutant, hour) layout costs ~85 B/row but needs
# 3.39 rows per German station-hour (measured), i.e. ~290 B per station-hour.
BYTES_READING_NARROW_PER_STATION_HOUR = 85 * 3.39
BYTES_WEATHER = 100          # 6 weather columns per modeled point-hour
BYTES_DAILY = 160            # mean/max/count per pollutant per station-day
BYTES_FORECAST = 60
BYTES_FIRE = 90
BYTES_ANOMALY = 200

RAW_RETENTION_DAYS = 97  # 90-day policy + up to 7 days until a weekly partition is fully expired
DAILY_BACKFILL_YEARS = 3     # long-term daily history backfilled at launch
# Hourly rows kept forever around festivals, measured stations of the relevant
# region only (+-3 days = 7 d per event): Deepavali + Bhogi for TN/Kerala,
# New Year's Eve for Germany and UAE.
EVENT_STATION_DAYS_PER_YEAR = (25 + 10) * 7 * 2 + (420 + 40) * 7
EVENT_YEARS = 5
FORECAST_ENTITIES, FORECAST_HORIZON_H, FORECAST_KEEP_DAYS = 120, 48, 30
FIRES_PER_DAY, FIRE_KEEP_DAYS = 1500, 90   # south-India peak season is the driver
ANOMALIES_PER_DAY, ANOMALY_KEEP_YEARS = 50, 3
OFFICIAL_ROWS_PER_HOUR, OFFICIAL_KEEP_DAYS = 120, 90   # CPCB sub-indices: ~17 stations x 7 pollutants
OVERHEAD_FACTOR = 1.15       # catalog, toast, indexes on secondary columns, vacuum slack


@dataclass
class Line:
    table: str
    rows: float
    bytes_per_row: float
    note: str

    @property
    def mb(self) -> float:
        return self.rows * self.bytes_per_row / 1024**2


def main() -> None:
    measured = sum(MEASURED_STATIONS.values())
    modeled = sum(MODELED_POINTS.values())
    entities = measured + modeled
    rows_per_day = entities * 24

    lines = [
        Line(f"readings (hourly, {RAW_RETENTION_DAYS} d)", rows_per_day * RAW_RETENTION_DAYS, BYTES_READING_WIDE,
             f"{entities} entities x 24 h x {RAW_RETENTION_DAYS} d"),
        Line(f"weather (hourly, {RAW_RETENTION_DAYS} d)", modeled * 24 * RAW_RETENTION_DAYS, BYTES_WEATHER,
             f"{modeled} modeled points"),
        Line("readings_daily (year 1 growth)", entities * 365, BYTES_DAILY, "kept forever"),
        Line("readings_daily (backfill)", entities * 365 * DAILY_BACKFILL_YEARS, BYTES_DAILY,
             f"{DAILY_BACKFILL_YEARS} years at launch"),
        Line("event_readings (hourly, kept)", EVENT_STATION_DAYS_PER_YEAR * 24 * EVENT_YEARS,
             BYTES_READING_WIDE, f"{EVENT_STATION_DAYS_PER_YEAR} station-days/yr x {EVENT_YEARS} yrs"),
        Line("forecasts (30 d)", FORECAST_ENTITIES * FORECAST_HORIZON_H * FORECAST_KEEP_DAYS,
             BYTES_FORECAST, "1 run/day kept for MAE scoring"),
        Line("fire_events (90 d)", FIRES_PER_DAY * FIRE_KEEP_DAYS, BYTES_FIRE, "NASA FIRMS"),
        Line("official_aqi (CPCB, 90 d)", OFFICIAL_ROWS_PER_HOUR * 24 * OFFICIAL_KEEP_DAYS, 60, "sub-index snapshots"),
        Line("anomalies (3 y)", ANOMALIES_PER_DAY * 365 * ANOMALY_KEEP_YEARS, BYTES_ANOMALY, ""),
        Line("stations/regions/ingestion_runs", 200_000, 150, "metadata + run log"),
    ]

    print(f"Hourly entities: {measured} measured stations + {modeled} modeled points = {entities}")
    print(f"Hourly reading rows/day: {rows_per_day:,}\n")
    print(f"{'table':34} {'rows':>12} {'B/row':>6} {'MB':>8}  note")
    total = 0.0
    for ln in lines:
        total += ln.mb
        print(f"{ln.table:34} {ln.rows:>12,.0f} {ln.bytes_per_row:>6.0f} {ln.mb:>8.1f}  {ln.note}")
    total *= OVERHEAD_FACTOR
    cap = NEON_FREE_BYTES / 1024**2
    print(f"\nTotal with {OVERHEAD_FACTOR:.2f}x overhead: {total:,.0f} MB "
          f"= {100 * total / cap:.0f}% of Neon free (1 GB), {100 * total / 500:.0f}% of Supabase free (500 MB)")
    yearly = entities * 365 * BYTES_DAILY / 1024**2 * OVERHEAD_FACTOR
    print(f"Steady-state growth: ~{yearly:.0f} MB/year (daily aggregates only; raw is capped by retention)")
    print(f"Years of headroom on Neon: ~{(cap * 0.8 - total) / yearly:.0f} (alert at 80%)")

    narrow = rows_per_day * RAW_RETENTION_DAYS * BYTES_READING_NARROW_PER_STATION_HOUR / 1024**2
    wide = lines[0].mb
    print(f"\nWhy a wide readings table: 90 d raw = {wide:.0f} MB wide vs ~{narrow:.0f} MB narrow (EAV)")


if __name__ == "__main__":
    main()
