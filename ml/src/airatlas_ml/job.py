"""Detect anomaly episodes for one region and store them with cause hints.

Re-runnable: episodes that END inside the window are replaced, and detection looks 3 days further
back so an episode that started before the window is rebuilt whole rather than truncated.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import psycopg

from airatlas_ingest.config import Region
from airatlas_ingest.events import EVENTS

from .anomaly import FLOORS, METHOD, Episode, detect
from .causes import Context, Fire, haversine_km, hints_for

BASELINE_DAYS = 8      # 7 days of same-hour neighbours + slack
STRADDLE_DAYS = 3      # rebuild episodes that began just before the window
CO_OCCUR = timedelta(hours=3)
PEER_RADIUS_KM = 100.0  # "area-wide" means neighbours, not the whole region (Germany is 900 km long)
POLLUTANTS = tuple(FLOORS)


def _measured_stations(conn, region_id: int) -> list[dict]:
    cur = conn.execute("""select id, st_y(geom) as lat, st_x(geom) as lon, kind, station_type
                          from stations where region_id = %s and active and kind <> 'modeled'""", (region_id,))
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _series(conn, ids: list[int], since: datetime) -> dict[int, dict[str, dict[datetime, float]]]:
    out: dict[int, dict[str, dict[datetime, float]]] = defaultdict(lambda: defaultdict(dict))
    rows = conn.execute(f"""select station_id, ts, {", ".join(POLLUTANTS)} from readings
                            where station_id = any(%s) and ts >= %s""", (ids, since)).fetchall()
    for sid, ts, *vals in rows:
        for p, v in zip(POLLUTANTS, vals):
            if v is not None:
                out[sid][p][ts] = v
    return out


def _nearest_model_points(conn, region_id: int, ids: list[int]) -> dict[int, int]:
    """Measured station -> nearest modeled point in the same region (for wind, rain and dust)."""
    rows = conn.execute("""select s.id, m.id from stations s
                           cross join lateral (select id from stations m
                                               where m.region_id = %s and m.kind = 'modeled'
                                               order by m.geom <-> s.geom limit 1) m
                           where s.id = any(%s)""", (region_id, ids)).fetchall()
    return dict(rows)


def _weather(conn, point_ids: list[int], since: datetime):
    out: dict[int, dict[datetime, tuple]] = defaultdict(dict)
    for pid, ts, d, s, p in conn.execute("""select station_id, ts, wind_dir_deg, wind_ms, precip_mm from weather
                                           where station_id = any(%s) and ts >= %s""", (point_ids, since)):
        out[pid][ts] = (d, s, p)
    return out


def _dust(conn, point_ids: list[int], since: datetime):
    out: dict[int, dict[datetime, float]] = defaultdict(dict)
    for pid, ts, v in conn.execute("""select station_id, ts, dust from readings
                                     where station_id = any(%s) and ts >= %s and dust is not null""", (point_ids, since)):
        out[pid][ts] = v
    return out


def _fires(conn, region_id: int, since: datetime) -> list[Fire]:
    rows = conn.execute("""select lat::float8, lon::float8, frp, detected_at, persistent from fire_events_flagged
                           where region_id = %s and detected_at >= %s""", (region_id, since)).fetchall()
    return [Fire(*r) for r in rows]


def _festival(region: Region, at: datetime) -> str | None:
    for ev in EVENTS:
        if region.code in ev.regions:
            start, end = ev.window(region.code)
            if start <= at < end:
                return ev.label.replace("_", " ").rsplit(" ", 1)[0].title().replace("Years", "Year's")
    return None


def _window(series: dict[datetime, object], start: datetime, end: datetime) -> list:
    return [v for t, v in series.items() if start <= t <= end]


def detect_region(conn: psycopg.Connection, region: Region, days: int, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    window_start = now - timedelta(days=days)
    detect_from = window_start - timedelta(days=STRADDLE_DAYS)
    fetch_from = detect_from - timedelta(days=BASELINE_DAYS)

    stations = _measured_stations(conn, region.id)
    ids = [s["id"] for s in stations]
    series = _series(conn, ids, fetch_from)

    found: list[tuple[dict, Episode]] = []
    for s in stations:
        for p, ser in series.get(s["id"], {}).items():
            for ep in detect(ser, p, since=detect_from):
                if ep.ends_at >= window_start:
                    found.append((s, ep))

    # Neighbours within PEER_RADIUS_KM (including the station itself) that measure each pollutant.
    pos = {s["id"]: (s["lat"], s["lon"]) for s in stations}
    neighbours = {a: {b for b in ids if haversine_km(*pos[a], *pos[b]) <= PEER_RADIUS_KM} for a in ids}
    by_pollutant: dict[str, list[tuple[int, Episode]]] = defaultdict(list)
    for s, ep in found:
        by_pollutant[ep.pollutant].append((s["id"], ep))

    nearest = _nearest_model_points(conn, region.id, ids) if found else {}
    points = list(set(nearest.values()))
    weather = _weather(conn, points, detect_from - timedelta(days=1)) if points else {}
    dust = _dust(conn, points, detect_from - timedelta(days=1)) if points else {}
    fires = _fires(conn, region.id, detect_from - timedelta(days=1)) if found else []

    rows = []
    for s, ep in found:
        near = neighbours[s["id"]]
        measuring = sum(1 for sid in near if series.get(sid, {}).get(ep.pollutant))
        peers = {sid for sid, other in by_pollutant[ep.pollutant]
                 if sid in near and other.starts_at - CO_OCCUR <= ep.peak_at <= other.ends_at + CO_OCCUR}
        pt = nearest.get(s["id"])
        wx = _window(weather.get(pt, {}), ep.starts_at - timedelta(hours=6), ep.peak_at)
        ctx = Context(
            lat=s["lat"], lon=s["lon"], pollutant=ep.pollutant, station_type=s["station_type"],
            wind=[(d, sp) for d, sp, _ in wx if d is not None and sp is not None],
            precip_mm=sum(p for *_, p in wx if p is not None) if wx else None,
            dust_max=max(_window(dust.get(pt, {}), ep.starts_at - timedelta(hours=3), ep.ends_at), default=None),
            fires=[f for f in fires if ep.starts_at - timedelta(hours=24) <= f.detected_at <= ep.peak_at],
            co_stations=(len(peers), measuring),
            festival=_festival(region, ep.peak_at),
            hours=ep.hours,
            ratio=ep.ratio,
        )
        hints = hints_for(ctx)
        rows.append((s["id"], ep.peak_at, ep.pollutant, ep.peak, ep.baseline, ep.z, METHOD,
                     json.dumps([h.to_json() for h in hints]), ep.starts_at, ep.ends_at,
                     json.dumps({"hours": ep.hours, "ratio": round(ep.ratio, 2) if ep.ratio else None})))

    with conn.transaction():
        deleted = conn.execute("""delete from anomalies where method = %s and ends_at >= %s
                                  and station_id = any(%s)""", (METHOD, window_start, ids)).rowcount
        if rows:
            with conn.cursor() as cur:
                cur.executemany(
                    """insert into anomalies (station_id, ts, pollutant, value, baseline, score, method, cause_hints,
                                              starts_at, ends_at, details)
                       values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
                       on conflict (station_id, pollutant, method, starts_at) do update set
                         ts = excluded.ts, value = excluded.value, baseline = excluded.baseline, score = excluded.score,
                         cause_hints = excluded.cause_hints, ends_at = excluded.ends_at, details = excluded.details""",
                    rows,
                )
    kinds = defaultdict(int)
    for r in rows:
        for h in json.loads(r[7]):
            kinds[h["kind"]] += 1
    return {"stations": len(ids), "episodes": len(rows), "replaced": deleted, "hint_kinds": dict(kinds)}
