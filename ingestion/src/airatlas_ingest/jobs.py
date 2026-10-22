"""Jobs run by GitHub Actions. Each (job, region, source) is its own tracked run, so one failing
source never blocks the others; the process exits non-zero if any of them failed."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

import psycopg

from . import boundaries, db, logs
from .adapters.cpcb import CpcbAdapter
from .adapters.firms import FirmsAdapter
from .adapters.openaq import OpenAQAdapter
from .adapters.openmeteo import OpenMeteoAdapter
from .adapters.uba import UbaAdapter
from .config import Region, Settings
from .events import EVENTS
from .models import StationKey

log = logs.get(__name__)
RAW_RETENTION = timedelta(days=90)


def _hour_floor(t: datetime) -> datetime:
    return t.replace(minute=0, second=0, microsecond=0)


def _require_boundaries(conn: psycopg.Connection, region: Region) -> None:
    if db.admin_area_count(conn, region.id) == 0:
        raise RuntimeError(f"no admin areas for {region.code}; run `python -m airatlas_ingest boundaries --region {region.code}`")


def _run_each(conn, job: str, region: Region | None, steps: dict[str, Callable[[db.Run], None]]) -> int:
    failures = 0
    for source, step in steps.items():
        try:
            with db.tracked_run(conn, job, region.code if region else None, source) as run:
                step(run)
        except Exception:
            failures += 1
    return failures


# --- hourly: measured sources -------------------------------------------------------------
def _cpcb(conn, settings: Settings, region: Region, run: db.Run) -> None:
    stations, official = CpcbAdapter(settings.data_gov_in_api_key).fetch_state(region.cpcb_state, run.rejected)
    db.upsert_stations(conn, "cpcb", stations)
    run.fetched = len(official)
    run.written = db.write_official(conn, official, run.rejected)
    run.details["stations"] = len(stations)


def _uba(conn, settings: Settings, region: Region, run: db.Run, start: datetime | None = None, end: datetime | None = None) -> None:
    uba = UbaAdapter()
    db.upsert_stations(conn, "uba", uba.discover())
    end = end or _hour_floor(datetime.now(timezone.utc))
    start = start or end - timedelta(hours=6)  # overlap: UBA publishes with ~2-3 h delay and revises
    rows = uba.hourly(start, end, run.rejected)
    run.fetched += len(rows)
    run.written += db.write_readings(conn, "uba", rows, run.rejected)


def _openaq_discover(conn, settings: Settings, region: Region, run: db.Run) -> OpenAQAdapter:
    oaq = OpenAQAdapter(settings.openaq_api_key, per_minute=settings.openaq_rpm)
    stations = oaq.discover(region.openaq_query, region.openaq_exclude_providers, run.rejected)
    db.upsert_stations(conn, "openaq", stations)  # boundary lookup drops neighbours caught by the bbox
    return oaq


def _openaq_sensors(conn, region: Region):
    for ext_id, station_id, meta, _lat, _lon in db.region_stations(conn, "openaq", region.id):
        for sensor_id, (parameter, units) in meta.get("sensors", {}).items():
            yield ext_id, station_id, meta, sensor_id, parameter, units


def _openaq(conn, settings: Settings, region: Region, run: db.Run) -> None:
    """Incremental: only locations whose datetimeLast moved past what we already have.
    The first run (or after an outage) catches up to 7 days back."""
    oaq = _openaq_discover(conn, settings, region, run)
    now = _hour_floor(datetime.now(timezone.utc))
    rows = db.region_stations(conn, "openaq", region.id)
    latest = db.latest_reading_ts(conn, [r[1] for r in rows])
    skipped = 0
    for ext_id, station_id, meta, sensor_id, parameter, units in _openaq_sensors(conn, region):
        last = latest.get(station_id)
        source_last = datetime.fromisoformat(meta["datetime_last"].replace("Z", "+00:00"))
        if last and source_last < last + timedelta(hours=1):
            skipped += 1
            continue
        start = max(last + timedelta(minutes=30), now - timedelta(days=7)) if last else now - timedelta(days=2)
        try:
            readings = oaq.hours(sensor_id, parameter, units, StationKey(source="openaq", external_id=ext_id),
                                 start, now + timedelta(hours=1), run.rejected)
        except Exception as e:  # one broken sensor must not stop the region
            run.errors.append(f"sensor {sensor_id}: {logs.redact(str(e))[:200]}")
            continue
        run.fetched += len(readings)
        run.written += db.write_readings(conn, "openaq", readings, run.rejected)
    run.details.update(sensors_skipped_no_new_data=skipped, api_calls=oaq.http.calls)


def hourly(conn: psycopg.Connection, settings: Settings, region: Region) -> int:
    _require_boundaries(conn, region)
    db.ensure_partitions(conn)
    handlers = {"cpcb": _cpcb, "uba": _uba, "openaq": _openaq}
    return _run_each(conn, "hourly", region, {
        s: (lambda run, s=s: handlers[s](conn, settings, region, run)) for s in region.hourly_sources
    })


# --- every 3 h: modeled AQ + weather, fires ------------------------------------------------
def _points(conn, region: Region) -> list[tuple[StationKey, float, float]]:
    rows = db.region_stations(conn, "open_meteo", region.id, kind="modeled")
    return [(StationKey(source="open_meteo", external_id=ext), lat, lon) for ext, _sid, _m, lat, lon in rows]


def modeled(conn: psycopg.Connection, settings: Settings, region: Region) -> int:
    _require_boundaries(conn, region)
    db.ensure_partitions(conn)
    if not _points(conn, region):
        boundaries.ensure_model_points(conn, region)
    om = OpenMeteoAdapter()

    def aq(run: db.Run) -> None:
        rows = om.air_quality(_points(conn, region), run.rejected, past_hours=6)
        run.fetched, run.written = len(rows), db.write_readings(conn, "open_meteo", rows, run.rejected)

    def weather(run: db.Run) -> None:
        rows = om.weather(_points(conn, region), run.rejected, past_hours=6)
        run.fetched, run.written = len(rows), db.write_weather(conn, rows, run.rejected)

    def fires(run: db.Run) -> None:
        rows = FirmsAdapter(settings.firms_map_key).fetch(region.id, region.bbox, run.rejected, days=1)
        run.fetched, run.written = len(rows), db.write_fires(conn, rows)

    return _run_each(conn, "modeled", region, {"open_meteo": aq, "open_meteo_weather": weather, "firms": fires})


# --- daily maintenance ----------------------------------------------------------------------
_AGG_COLS = ", ".join(f"avg({p})::real, max({p})::real" for p in ("pm25", "pm10", "no2", "o3", "so2", "co"))
AGGREGATE_DAILY = f"""
insert into readings_daily (station_id, day, source_id, n_hours,
    pm25_mean, pm25_max, pm10_mean, pm10_max, no2_mean, no2_max, o3_mean, o3_max,
    so2_mean, so2_max, co_mean, co_max, nh3_mean, dust_mean, dust_max)
select r.station_id, (r.ts at time zone g.timezone)::date, mode() within group (order by r.source_id), count(*),
       {_AGG_COLS}, avg(nh3)::real, avg(dust)::real, max(dust)::real
from readings r join stations s on s.id = r.station_id join regions g on g.id = s.region_id
where r.ts >= %(since)s
group by 1, 2
on conflict (station_id, day) do update set
    source_id = excluded.source_id, n_hours = excluded.n_hours,
    pm25_mean = excluded.pm25_mean, pm25_max = excluded.pm25_max, pm10_mean = excluded.pm10_mean, pm10_max = excluded.pm10_max,
    no2_mean = excluded.no2_mean, no2_max = excluded.no2_max, o3_mean = excluded.o3_mean, o3_max = excluded.o3_max,
    so2_mean = excluded.so2_mean, so2_max = excluded.so2_max, co_mean = excluded.co_mean, co_max = excluded.co_max,
    nh3_mean = excluded.nh3_mean, dust_mean = excluded.dust_mean, dust_max = excluded.dust_max
"""

AGGREGATE_WEATHER_DAILY = """
insert into weather_daily (station_id, day, temp_mean, rh_mean, precip_sum, wind_mean)
select w.station_id, (w.ts at time zone g.timezone)::date, avg(temp_c), avg(rh_pct), sum(precip_mm), avg(wind_ms)
from weather w join stations s on s.id = w.station_id join regions g on g.id = s.region_id
where w.ts >= %(since)s
group by 1, 2 having count(*) >= 20
on conflict (station_id, day) do update set temp_mean = excluded.temp_mean, rh_mean = excluded.rh_mean,
    precip_sum = excluded.precip_sum, wind_mean = excluded.wind_mean
"""

ARCHIVE_HOLDS = """
insert into readings_archive
select r.* from readings r
join stations s on s.id = r.station_id and s.kind <> 'modeled'
join retention_holds h on h.region_id = s.region_id and r.ts >= h.starts_at and r.ts < h.ends_at
where h.ends_at < now()
on conflict (station_id, ts) do nothing
"""


def aggregate_daily(conn: psycopg.Connection, since: datetime) -> tuple[int, int]:
    with conn.transaction():
        a = conn.execute(AGGREGATE_DAILY, {"since": since}).rowcount
        b = conn.execute(AGGREGATE_WEATHER_DAILY, {"since": since}).rowcount
    return a, b


def seed_holds(conn: psycopg.Connection) -> int:
    from .config import REGIONS
    n = 0
    with conn.transaction():
        for ev in EVENTS:
            for code in ev.regions:
                start, end = ev.window(code)
                n += conn.execute(
                    """insert into retention_holds (label, region_id, starts_at, ends_at) values (%s, %s, %s, %s)
                       on conflict (label, region_id) do update set starts_at = excluded.starts_at, ends_at = excluded.ends_at""",
                    (ev.label, REGIONS[code].id, start, end),
                ).rowcount
    return n


def maintenance(conn: psycopg.Connection, settings: Settings) -> int:
    def run_all(run: db.Run) -> None:
        d = run.details
        with conn.transaction():
            conn.execute("select ensure_weekly_partitions('readings', 1, 3), ensure_weekly_partitions('weather', 1, 3)")
        d["daily_rows"], d["weather_daily_rows"] = aggregate_daily(conn, datetime.now(timezone.utc) - timedelta(days=4))
        d["holds"] = seed_holds(conn)
        with conn.transaction():
            d["archived_rows"] = conn.execute(ARCHIVE_HOLDS).rowcount
            d["dropped_partitions"] = [r[0] for r in conn.execute(
                "select drop_old_partitions('readings', %s) union all select drop_old_partitions('weather', %s)",
                (RAW_RETENTION, RAW_RETENTION))]
            d["deleted"] = {
                t: conn.execute(f"delete from {t} where {col} < now() - %s::interval", (keep,)).rowcount
                for t, col, keep in (("official_aqi", "reported_at", "90 days"), ("fire_events", "detected_at", "90 days"),
                                     ("forecasts", "issued_at", "30 days"), ("ingestion_runs", "started_at", "180 days"),
                                     ("anomalies", "ts", "3 years"))
            }
        d["storage_bytes"] = conn.execute("select pg_database_size(current_database())").fetchone()[0]
        d["largest_tables"] = dict(conn.execute(
            """select c.relname, pg_total_relation_size(c.oid) from pg_class c
               join pg_namespace n on n.oid = c.relnamespace
               where n.nspname = current_schema() and c.relkind in ('r', 'p') and not c.relispartition
               order by 2 desc limit 8""").fetchall())
        # partitions are relispartition; report their parents' totals
        d["largest_tables"].update(dict(conn.execute(
            """select p.relname, sum(pg_total_relation_size(c.oid)) from pg_inherits i
               join pg_class c on c.oid = i.inhrelid join pg_class p on p.oid = i.inhparent group by 1""").fetchall()))
        run.written = d["daily_rows"] + d["archived_rows"]
        log.info("storage", mb=round(d["storage_bytes"] / 2**20, 1))

    return _run_each(conn, "maintenance", None, {"maintenance": run_all})


# --- backfill (manual, resumable) -----------------------------------------------------------
def _progress(conn, source: str, station_id: int, kind: str) -> datetime | None:
    row = conn.execute("select done_from from backfill_progress where source_id = %s and station_id = %s and kind = %s",
                       (db.source_id(conn, source), station_id, kind)).fetchone()
    return row[0] if row else None


def _save_progress(conn, source: str, station_id: int, kind: str, done_from: datetime, done_until: datetime) -> None:
    with conn.transaction():
        conn.execute("""insert into backfill_progress (source_id, station_id, kind, done_from, done_until) values (%s, %s, %s, %s, %s)
                        on conflict (source_id, station_id, kind) do update set done_from = least(backfill_progress.done_from, excluded.done_from),
                        done_until = greatest(backfill_progress.done_until, excluded.done_until), updated_at = now()""",
                     (db.source_id(conn, source), station_id, kind, done_from, done_until))


def _chunks_back(until: datetime, target_from: datetime, step: timedelta):
    """Yield (start, end) windows walking backwards from `until` to `target_from`."""
    end = until
    while end > target_from:
        start = max(end - step, target_from)
        yield start, end
        end = start


def _bf_uba(conn, run: db.Run, region: Region, kind: str, now: datetime, target: datetime) -> None:
    uba = UbaAdapter()
    db.upsert_stations(conn, "uba", uba.discover())
    step = timedelta(days=7) if kind == "hourly" else timedelta(days=180)
    for s, e in _chunks_back(_progress(conn, "uba", -region.id, kind) or now, target, step):
        if kind == "hourly":
            rows = uba.hourly(s, e, run.rejected)
            run.written += db.write_readings(conn, "uba", rows, run.rejected)
        else:
            rows = uba.daily(s.date(), e.date(), run.rejected)
            run.written += db.write_daily(conn, "uba", rows, run.rejected)
        run.fetched += len(rows)
        _save_progress(conn, "uba", -region.id, kind, s, e)


def _bf_openaq(conn, settings: Settings, run: db.Run, region: Region, kind: str, now: datetime, target: datetime) -> None:
    oaq = _openaq_discover(conn, settings, region, run)
    step = timedelta(days=40) if kind == "hourly" else timedelta(days=900)  # stays under 1000 rows/page
    by_station: dict[int, list] = {}
    for ext_id, station_id, _meta, sensor_id, parameter, units in _openaq_sensors(conn, region):
        by_station.setdefault(station_id, []).append((ext_id, sensor_id, parameter, units))
    for station_id, sensors in by_station.items():
        done = _progress(conn, "openaq", station_id, kind)
        if done is not None and done <= target:
            continue
        for ext_id, sensor_id, parameter, units in sensors:
            key = StationKey(source="openaq", external_id=ext_id)
            for s, e in _chunks_back(done or now, target, step):
                try:
                    if kind == "hourly":
                        rows = oaq.hours(sensor_id, parameter, units, key, s, e, run.rejected)
                        run.written += db.write_readings(conn, "openaq", rows, run.rejected)
                    else:
                        rows = oaq.days(sensor_id, parameter, units, key, s.date(), e.date(), run.rejected)
                        run.written += db.write_daily(conn, "openaq", rows, run.rejected)
                    run.fetched += len(rows)
                except Exception as ex:
                    run.errors.append(f"sensor {sensor_id}: {logs.redact(str(ex))[:200]}")
        _save_progress(conn, "openaq", station_id, kind, target, now)
    run.details["api_calls"] = oaq.http.calls


def _bf_open_meteo(conn, run: db.Run, region: Region, kind: str, now: datetime, target: datetime) -> None:
    if not _points(conn, region):
        boundaries.ensure_model_points(conn, region)
    om = OpenMeteoAdapter()
    points = _points(conn, region)
    if kind == "hourly":
        for s, e in _chunks_back(_progress(conn, "open_meteo", -region.id, kind) or now, target, timedelta(days=30)):
            aq = om.air_quality(points, run.rejected, start=s.date(), end=e.date())
            wx = om.weather(points, run.rejected, start=s.date(), end=e.date())
            run.fetched += len(aq) + len(wx)
            run.written += db.write_readings(conn, "open_meteo", aq, run.rejected) + db.write_weather(conn, wx, run.rejected)
            _save_progress(conn, "open_meteo", -region.id, kind, s, e)
    else:
        # One year per run: a location-year weighs ~26 calls, and the free tier allows 10,000/day.
        until = _progress(conn, "open_meteo", -region.id, kind) or now - timedelta(days=5)  # ERA5 lags ~5 days
        for s, e in _chunks_back(until, target, timedelta(days=365)):
            rows = om.weather_daily(points, region.tz.key, s.date(), e.date(), run.rejected)
            run.fetched += len(rows)
            run.written += db.write_weather_daily(conn, rows, run.rejected)
            _save_progress(conn, "open_meteo", -region.id, kind, s, e)
            break


def backfill(conn: psycopg.Connection, settings: Settings, region: Region, source: str, kind: str, days: int) -> int:
    """Walk backwards from now (or from where the last run stopped) to now - days. Re-runnable."""
    _require_boundaries(conn, region)
    db.ensure_partitions(conn)
    now = _hour_floor(datetime.now(timezone.utc))
    target = now - timedelta(days=days)
    if kind == "hourly":
        target = max(target, now - RAW_RETENTION + timedelta(days=1))  # older raw would be dropped anyway

    def step(run: db.Run) -> None:
        if source == "uba" and kind in ("hourly", "daily"):
            _bf_uba(conn, run, region, kind, now, target)
        elif source == "openaq" and kind in ("hourly", "daily"):
            _bf_openaq(conn, settings, run, region, kind, now, target)
        elif source == "open_meteo" and kind in ("hourly", "weather_daily"):
            _bf_open_meteo(conn, run, region, kind, now, target)
        elif source == "firms":
            firms = FirmsAdapter(settings.firms_map_key)
            for s, _e in _chunks_back(now, max(target, now - timedelta(days=60)), timedelta(days=5)):
                rows = firms.fetch(region.id, region.bbox, run.rejected, days=5, start=s.date())
                run.fetched += len(rows)
                run.written += db.write_fires(conn, rows)
        else:
            raise ValueError(f"unsupported backfill: source={source} kind={kind}")
        if kind == "hourly":
            run.details["daily_rows"] = aggregate_daily(conn, target)[0]

    return _run_each(conn, f"backfill:{kind}", region, {source: step})


def backfill_events(conn: psycopg.Connection, settings: Settings, region: Region) -> int:
    """Hourly data for past festival windows, straight into readings_archive."""
    _require_boundaries(conn, region)
    seed_holds(conn)
    now = datetime.now(timezone.utc)
    windows = [(ev.label, *(t.astimezone(timezone.utc) for t in ev.window(region.code)))
               for ev in EVENTS if region.code in ev.regions]
    windows = [w for w in windows if w[2] <= now]

    def step(run: db.Run) -> None:
        uba = oaq = None
        for label, start, end in windows:
            have = conn.execute("""select count(*) from readings_archive r join stations s on s.id = r.station_id
                                   where s.region_id = %s and r.ts >= %s and r.ts < %s""",
                                (region.id, start, end)).fetchone()[0]
            if have:
                continue
            if "uba" in region.hourly_sources:
                if uba is None:
                    uba = UbaAdapter()
                    db.upsert_stations(conn, "uba", uba.discover())
                rows = uba.hourly(start, end, run.rejected)
                source = "uba"
            else:
                if oaq is None:
                    oaq = _openaq_discover(conn, settings, region, run)
                rows = []
                for ext_id, _sid, _m, sensor_id, parameter, units in _openaq_sensors(conn, region):
                    try:
                        rows += oaq.hours(sensor_id, parameter, units, StationKey(source="openaq", external_id=ext_id),
                                          start, end, run.rejected)
                    except Exception as ex:
                        run.errors.append(f"{label} sensor {sensor_id}: {logs.redact(str(ex))[:160]}")
                source = "openaq"
            run.fetched += len(rows)
            run.written += db.write_readings(conn, source, rows, run.rejected, table="readings_archive")
            run.details.setdefault("windows", []).append(label)

    return _run_each(conn, "backfill:events", region, {"events": step})


def status(conn: psycopg.Connection) -> list[dict]:
    rows = conn.execute(
        """select distinct on (job, region, source) job, region, source, status, started_at, rows_written, rows_rejected, error
           from ingestion_runs order by job, region, source, started_at desc""").fetchall()
    cols = ("job", "region", "source", "status", "started_at", "written", "rejected", "error")
    return [dict(zip(cols, r)) for r in rows]


def to_json(obj) -> str:
    return json.dumps(obj, default=str, indent=2)
