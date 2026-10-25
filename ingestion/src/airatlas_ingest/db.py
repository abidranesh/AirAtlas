"""Postgres access. Every write is set-based (COPY into a temp table, then one merge statement)
because each round trip to Neon costs ~100-400 ms; row-by-row inserts would not fit in a cron slot.

Works through Neon's PgBouncer (transaction pooling): no session state is relied on, temp tables
are `on commit drop`, locks are transaction-scoped, and server-side prepared statements are off.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import psycopg

from . import logs
from .config import MIGRATIONS_DIR
from .models import POLLUTANTS, DailyReading, FireEvent, OfficialSubIndex, Reading, StationIn, StationKey, WeatherDaily, WeatherObs

log = logs.get(__name__)
MIGRATION_LOCK = 0x41495241  # "AIRA"


_url: str | None = None  # remembered so a run can still record its status after a dropped connection


def connect(url: str) -> psycopg.Connection:
    global _url
    _url = url
    # autocommit: every `with conn.transaction()` block is its own real transaction, so a failure
    # in one source's run can never roll back another source's already-written rows.
    return psycopg.connect(url, autocommit=True, prepare_threshold=None, connect_timeout=30,
                           application_name="airatlas-ingest")


# --- migrations -------------------------------------------------------------------------
def migrate(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending *.sql files in order, atomically, safe against concurrent runners."""
    applied = []
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(%s)", (MIGRATION_LOCK,))
        conn.execute("create table if not exists schema_migrations (version text primary key, applied_at timestamptz not null default now())")
        done = {r[0] for r in conn.execute("select version from schema_migrations")}
        for f in sorted(directory.glob("*.sql")):
            if f.stem in done:
                continue
            conn.execute(f.read_text(encoding="utf-8"))
            conn.execute("insert into schema_migrations (version) values (%s)", (f.stem,))
            applied.append(f.stem)
    return applied


def ensure_partitions(conn: psycopg.Connection) -> None:
    with conn.transaction():
        conn.execute("select ensure_weekly_partitions('readings', 14, 2), ensure_weekly_partitions('weather', 14, 2)")


# --- lookups ------------------------------------------------------------------------------
_source_ids: dict[str, int] = {}


def source_id(conn: psycopg.Connection, code: str) -> int:
    if code not in _source_ids:
        row = conn.execute("select id from sources where code = %s", (code,)).fetchone()
        if row is None:
            raise KeyError(f"unknown source {code!r}")
        _source_ids[code] = row[0]
    return _source_ids[code]


def station_ids(conn: psycopg.Connection, keys: Iterable[StationKey]) -> dict[StationKey, int]:
    keys = list(set(keys))
    if not keys:
        return {}
    rows = conn.execute(
        """select s.code, ss.external_id, ss.station_id
           from station_sources ss join sources s on s.id = ss.source_id
           join unnest(%s::text[], %s::text[]) as k(code, ext) on k.code = s.code and k.ext = ss.external_id""",
        ([k.source for k in keys], [k.external_id for k in keys]),
    ).fetchall()
    return {StationKey(source=c, external_id=e): sid for c, e, sid in rows}


def region_stations(conn: psycopg.Connection, source: str, region_id: int, kind: str | None = None) -> list[tuple[str, int, dict, float, float]]:
    """(external_id, station_id, link meta, lat, lon) for a source's active stations in a region."""
    return conn.execute(
        """select ss.external_id, s.id, ss.meta, st_y(s.geom), st_x(s.geom)
           from station_sources ss join stations s on s.id = ss.station_id
           where ss.source_id = %s and s.region_id = %s and s.active and (%s::text is null or s.kind = %s)
           order by s.id""",
        (source_id(conn, source), region_id, kind, kind),
    ).fetchall()


def latest_reading_ts(conn: psycopg.Connection, station_ids_: list[int]) -> dict[int, datetime]:
    if not station_ids_:
        return {}
    rows = conn.execute(
        "select station_id, max(ts) from readings where station_id = any(%s) and ts > now() - interval '14 days' group by 1",
        (station_ids_,),
    ).fetchall()
    return dict(rows)


def admin_area_count(conn: psycopg.Connection, region_id: int) -> int:
    return conn.execute("select count(*) from admin_areas where region_id = %s", (region_id,)).fetchone()[0]


# --- stations -------------------------------------------------------------------------------
_NORM = "lower(regexp_replace({}, '[^[:alnum:]]', '', 'g'))"

_MATCH_OTHER_SOURCE = f"""
update _st i set station_id = m.id
from (
    select distinct on (i2.external_id) i2.external_id, cand.id
    from _st i2
    cross join lateral (
        select s.id,
               st_distance(s.geom::geography, st_setsrid(st_makepoint(i2.lon, i2.lat), 4326)::geography) as d,
               {_NORM.format('s.name')} = {_NORM.format('i2.name')} as same_name
        from stations s
        where s.kind = i2.kind and s.kind <> 'modeled'
          and s.geom && st_expand(st_setsrid(st_makepoint(i2.lon, i2.lat), 4326), 0.05)
          and not exists (select 1 from station_sources ss where ss.station_id = s.id and ss.source_id = %(src)s)
    ) cand
    where i2.station_id is null and (cand.d <= 250 or (cand.same_name and cand.d <= 5000))
    order by i2.external_id, cand.same_name desc, cand.d
) m
where i.external_id = m.external_id
"""

# Nearest admin area within 5 km: simplified boundaries cut off some coastal stations (Chennai, Dubai).
_ASSIGN_REGION = """
update stations s set (admin_area_id, region_id) = (
    select a.id, a.region_id from admin_areas a
    where a.geom && st_expand(s.geom, 0.05)
      and st_dwithin(a.geom::geography, s.geom::geography, 5000)
    order by st_distance(a.geom::geography, s.geom::geography) limit 1)
where s.id in (select station_id from _st) and s.admin_area_id is null
"""


def upsert_stations(conn: psycopg.Connection, source: str, stations: list[StationIn]) -> dict[str, int]:
    """Create or update stations; returns external_id -> station_id.

    Matching order: (1) this source's existing link, (2) a station of the same kind from another
    source within 250 m, or with the same normalised name within 5 km, (3) a new station.
    New stations are assigned to a region/admin area by boundary lookup.
    """
    if not stations:
        return {}
    src = source_id(conn, source)
    with conn.transaction():
        conn.execute("""create temp table _st (external_id text, name text, city text, lat float8, lon float8,
                        kind text, setting text, station_type text, license text, meta jsonb, station_id int) on commit drop""")
        with conn.cursor().copy("copy _st (external_id, name, city, lat, lon, kind, setting, station_type, license, meta) from stdin") as cp:
            for s in {s.external_id: s for s in stations}.values():
                cp.write_row((s.external_id, s.name, s.city, s.lat, s.lon, s.kind, s.setting, s.station_type, s.license, json.dumps(s.meta)))
        conn.execute("update _st i set station_id = ss.station_id from station_sources ss where ss.source_id = %s and ss.external_id = i.external_id", (src,))
        conn.execute(_MATCH_OTHER_SOURCE, {"src": src})
        conn.execute("update _st set station_id = nextval(pg_get_serial_sequence('stations', 'id')) where station_id is null")
        conn.execute("""insert into stations (id, name, city, geom, kind, setting, station_type)
                        select station_id, name, city, st_setsrid(st_makepoint(lon, lat), 4326), kind, setting, station_type
                        from _st i where not exists (select 1 from stations s where s.id = i.station_id)""")
        conn.execute("""insert into station_sources (source_id, external_id, station_id, license, meta)
                        select %s, external_id, station_id, license, meta from _st
                        on conflict (source_id, external_id) do update
                        set meta = excluded.meta, license = coalesce(excluded.license, station_sources.license)""", (src,))
        conn.execute("""update stations s set last_seen_at = now(), active = true,
                            city = coalesce(s.city, i.city), setting = coalesce(s.setting, i.setting),
                            station_type = coalesce(s.station_type, i.station_type)
                        from _st i where s.id = i.station_id""")
        conn.execute(_ASSIGN_REGION)
        return dict(conn.execute("select external_id, station_id from _st").fetchall())


# --- time series writes -------------------------------------------------------------------
def _resolve(conn, keys: Iterable[StationKey], rejected: Counter) -> dict[StationKey, int]:
    keys = set(keys)  # callers pass generators; read once
    ids = station_ids(conn, keys)
    rejected["unknown station"] += len(keys - ids.keys())
    return ids


_COLS = ", ".join(POLLUTANTS)
_MERGE = ", ".join(f"{p} = coalesce(excluded.{p}, {{t}}.{p})" for p in POLLUTANTS)
_PRIORITY_GUARD = """(select priority from sources where id = excluded.source_id)
                     >= (select priority from sources where id = {t}.source_id)"""


def write_readings(conn: psycopg.Connection, source: str, rows: list[Reading], rejected: Counter,
                   table: str = "readings") -> int:
    """Upsert hourly rows. Values from several sensors of one station-hour are merged.
    A lower-priority source never overwrites a higher-priority one; nulls never erase values."""
    if not rows:
        return 0
    src = source_id(conn, source)
    ids = _resolve(conn, (r.station for r in rows), rejected)
    merged: dict[tuple[int, datetime], dict[str, float]] = defaultdict(dict)
    for r in rows:
        if r.station in ids:
            merged[(ids[r.station], r.ts)].update(r.values)
    if not merged:
        return 0
    with conn.transaction():
        conn.execute(f"create temp table _rd (station_id int, ts timestamptz, {', '.join(p + ' real' for p in POLLUTANTS)}) on commit drop")
        with conn.cursor().copy(f"copy _rd (station_id, ts, {_COLS}) from stdin") as cp:
            for (sid, ts), vals in merged.items():
                cp.write_row((sid, ts, *(vals.get(p) for p in POLLUTANTS)))
        cur = conn.execute(
            f"""insert into {table} (station_id, ts, source_id, {_COLS})
                select station_id, ts, %s, {_COLS} from _rd
                on conflict (station_id, ts) do update
                set {_MERGE.format(t=table)}, source_id = excluded.source_id, ingested_at = now()
                where {_PRIORITY_GUARD.format(t=table)}""",
            (src,),
        )
        return cur.rowcount


_DAILY_COLS = [f"{p}_{a}" for p in ("pm25", "pm10", "no2", "o3", "so2", "co") for a in ("mean", "max")] + ["nh3_mean", "dust_mean", "dust_max"]


def write_daily(conn: psycopg.Connection, source: str, rows: list[DailyReading], rejected: Counter) -> int:
    """Source-provided daily values (backfill beyond the raw retention window)."""
    if not rows:
        return 0
    src = source_id(conn, source)
    ids = _resolve(conn, (r.station for r in rows), rejected)
    merged: dict[tuple[int, object], dict[str, float]] = defaultdict(dict)
    for r in rows:
        if r.station in ids:
            cell = merged[(ids[r.station], r.day)]
            cell.update({f"{p}_mean": v for p, v in r.means.items() if f"{p}_mean" in _DAILY_COLS})
            cell.update({f"{p}_max": v for p, v in r.maxes.items() if f"{p}_max" in _DAILY_COLS})
    cols = ", ".join(_DAILY_COLS)
    with conn.transaction():
        conn.execute(f"create temp table _dd (station_id int, day date, {', '.join(c + ' real' for c in _DAILY_COLS)}) on commit drop")
        with conn.cursor().copy(f"copy _dd (station_id, day, {cols}) from stdin") as cp:
            for (sid, day), vals in merged.items():
                cp.write_row((sid, day, *(vals.get(c) for c in _DAILY_COLS)))
        cur = conn.execute(
            f"""insert into readings_daily (station_id, day, source_id, {cols})
                select station_id, day, %s, {cols} from _dd
                on conflict (station_id, day) do update
                set {", ".join(f"{c} = coalesce(excluded.{c}, readings_daily.{c})" for c in _DAILY_COLS)},
                    source_id = excluded.source_id
                where readings_daily.n_hours is null
                  and {_PRIORITY_GUARD.format(t="readings_daily")}""",
            (src,),
        )
        return cur.rowcount


_WX = ("temp_c", "rh_pct", "precip_mm", "wind_ms", "wind_dir_deg", "pressure_hpa")


def write_weather(conn: psycopg.Connection, rows: list[WeatherObs], rejected: Counter) -> int:
    if not rows:
        return 0
    ids = _resolve(conn, (r.station for r in rows), rejected)
    data = {(ids[r.station], r.ts): r for r in rows if r.station in ids}
    with conn.transaction():
        conn.execute(f"create temp table _wx (station_id int, ts timestamptz, {', '.join(c + ' real' for c in _WX)}) on commit drop")
        with conn.cursor().copy(f"copy _wx (station_id, ts, {', '.join(_WX)}) from stdin") as cp:
            for (sid, ts), r in data.items():
                cp.write_row((sid, ts, *(getattr(r, c) for c in _WX)))
        cur = conn.execute(f"""insert into weather (station_id, ts, {', '.join(_WX)}) select * from _wx
                               on conflict (station_id, ts) do update set {', '.join(f'{c} = excluded.{c}' for c in _WX)}""")
        return cur.rowcount


def write_weather_daily(conn: psycopg.Connection, rows: list[WeatherDaily], rejected: Counter) -> int:
    if not rows:
        return 0
    ids = _resolve(conn, (r.station for r in rows), rejected)
    cols = ("temp_mean", "rh_mean", "precip_sum", "wind_mean")
    data = {(ids[r.station], r.day): r for r in rows if r.station in ids}
    with conn.transaction():
        conn.execute("create temp table _wd (station_id int, day date, temp_mean real, rh_mean real, precip_sum real, wind_mean real) on commit drop")
        with conn.cursor().copy("copy _wd from stdin") as cp:
            for (sid, day), r in data.items():
                cp.write_row((sid, day, *(getattr(r, c) for c in cols)))
        cur = conn.execute(f"""insert into weather_daily select * from _wd on conflict (station_id, day) do update
                               set {', '.join(f'{c} = coalesce(excluded.{c}, weather_daily.{c})' for c in cols)}""")
        return cur.rowcount


def write_official(conn: psycopg.Connection, rows: list[OfficialSubIndex], rejected: Counter) -> int:
    if not rows:
        return 0
    ids = _resolve(conn, (r.station for r in rows), rejected)
    data = {(ids[r.station], r.reported_at, r.pollutant): r for r in rows if r.station in ids}
    with conn.transaction():
        conn.execute("create temp table _oa (station_id int, reported_at timestamptz, pollutant text, sub_min real, sub_avg real, sub_max real) on commit drop")
        with conn.cursor().copy("copy _oa from stdin") as cp:
            for (sid, ts, p), r in data.items():
                cp.write_row((sid, ts, p, r.sub_min, r.sub_avg, r.sub_max))
        return conn.execute("insert into official_aqi select * from _oa on conflict do nothing").rowcount


def write_fires(conn: psycopg.Connection, rows: list[FireEvent]) -> int:
    if not rows:
        return 0
    with conn.transaction():
        conn.execute("""create temp table _fe (region_id smallint, detected_at timestamptz, lat numeric(8,5), lon numeric(8,5),
                        frp real, confidence text, satellite text, instrument text, daynight char(1)) on commit drop""")
        with conn.cursor().copy("copy _fe from stdin") as cp:
            for f in rows:
                cp.write_row((f.region_id, f.detected_at, round(f.lat, 5), round(f.lon, 5), f.frp, f.confidence, f.satellite, f.instrument, f.daynight))
        return conn.execute("""insert into fire_events (region_id, detected_at, lat, lon, frp, confidence, satellite, instrument, daynight)
                               select * from _fe on conflict do nothing""").rowcount


# --- run tracking ---------------------------------------------------------------------------
class Run:
    def __init__(self, conn: psycopg.Connection, job: str, region: str | None, source: str | None) -> None:
        self.conn = conn
        self.fetched = 0
        self.written = 0
        self.rejected: Counter = Counter()
        self.errors: list[str] = []
        self.details: dict = {}
        with conn.transaction():
            self.id = conn.execute(
                "insert into ingestion_runs (job, region, source) values (%s, %s, %s) returning id", (job, region, source)
            ).fetchone()[0]
            self.search_path = conn.execute("show search_path").fetchone()[0]

    def finish(self, status: str, error: str | None = None) -> None:
        details = {**self.details, "rejected_reasons": dict(self.rejected.most_common(10)), "errors": self.errors[:20]}
        sql = """update ingestion_runs set finished_at = now(), status = %s, rows_fetched = %s, rows_written = %s,
                 rows_rejected = %s, error = %s, details = %s where id = %s"""
        params = (status, self.fetched, self.written, sum(self.rejected.values()), error, json.dumps(details, default=str), self.id)
        try:
            with self.conn.transaction():
                self.conn.execute(sql, params)
        except (psycopg.OperationalError, psycopg.InterfaceError) as e:
            # Neon suspends idle compute and drops connections; record the outcome on a fresh one.
            log.warning("connection lost before recording run status; reconnecting", run_id=self.id, error=str(e)[:120])
            if _url is None:
                raise
            with psycopg.connect(_url, autocommit=True, prepare_threshold=None, connect_timeout=30) as fresh:
                fresh.execute(f"set search_path to {self.search_path}")
                fresh.execute(sql, params)


@contextmanager
def tracked_run(conn: psycopg.Connection, job: str, region: str | None, source: str | None) -> Iterator[Run]:
    run = Run(conn, job, region, source)
    logs.bind(job=job, region=region, source=source, run_id=run.id)
    try:
        yield run
    except Exception as e:
        if not conn.closed and conn.info.transaction_status not in (psycopg.pq.TransactionStatus.IDLE, psycopg.pq.TransactionStatus.UNKNOWN):
            conn.rollback()
        msg = logs.redact(f"{type(e).__name__}: {e}")[:1000]
        run.finish("failed", msg)
        log.error("run failed", error=msg, fetched=run.fetched, written=run.written)
        raise
    else:
        status = "partial" if run.errors else "success"
        run.finish(status)
        log.info("run finished", status=status, fetched=run.fetched, written=run.written,
                 rejected=sum(run.rejected.values()), errors=len(run.errors))
