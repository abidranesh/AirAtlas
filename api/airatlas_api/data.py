"""SQL and the read models built on it. Every query is bounded (one region, a time window, a LIMIT)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from airatlas_aqi import COMMON_SCALES, LOCAL_STANDARD, AqiStandard, get_standard, standard_for
from fastapi import HTTPException

from . import db
from .evaluate import HISTORY_HOURS, evaluate_station, summarize_area

REGION_COLS = "id, code, name, country_code, timezone, local_standard, st_asgeojson(bbox)::json as bbox"
STATION_COLS = """s.id, s.name, coalesce(s.city, a.name) as city, a.id as area_id, a.name as area, s.kind, s.setting,
                  s.station_type, round(st_y(s.geom)::numeric, 5)::float8 as lat, round(st_x(s.geom)::numeric, 5)::float8 as lon,
                  g.code as region"""
READING_COLS = "r.station_id, r.ts, r.pm25, r.pm10, r.no2, r.o3, r.so2, r.co, r.nh3, r.dust"
# Featured areas for the cross-region comparison (admin area names as stored).
FEATURED_AREAS = {"tamil_nadu": "Chennai", "kerala": "Ernakulam", "uae": "Dubai", "germany": "Berlin"}


def resolve_scale(region: str, scale: str) -> AqiStandard:
    if scale != "local" and scale not in COMMON_SCALES:
        raise HTTPException(422, f"scale must be 'local' or one of {list(COMMON_SCALES)}")
    return standard_for(region, scale)


def region_row(code: str) -> dict:
    row = db.fetch_one(f"select {REGION_COLS} from regions where code = %s", (code,))
    if row is None:
        raise HTTPException(404, f"unknown region {code!r}")
    return row


def regions() -> list[dict]:
    rows = db.fetch(f"""select {REGION_COLS},
                          (select count(*) from stations s where s.region_id = r.id and s.active and s.kind = 'reference') as reference_stations,
                          (select count(*) from stations s where s.region_id = r.id and s.active and s.kind = 'low_cost') as low_cost_stations,
                          (select count(*) from stations s where s.region_id = r.id and s.active and s.kind = 'modeled') as modeled_points
                       from regions r order by id""")
    return rows


def readings_for(station_ids: list[int], hours: int) -> dict[int, list[dict]]:
    rows = db.fetch(f"""select {READING_COLS} from readings r
                        where r.station_id = any(%s) and r.ts > now() - make_interval(hours => %s)
                        order by r.station_id, r.ts""", (station_ids, hours))
    out: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        out[r["station_id"]].append(r)
    return out


def official_for(station_ids: list[int]) -> dict[int, dict]:
    """Latest CPCB published sub-indices per station (last 6 h) -> official AQI = max sub-index."""
    rows = db.fetch("""select distinct on (station_id, pollutant) station_id, pollutant, reported_at, sub_avg
                       from official_aqi where station_id = any(%s) and reported_at > now() - interval '6 hours'
                       order by station_id, pollutant, reported_at desc""", (station_ids,))
    cpcb = get_standard("in_cpcb_naqi")
    by: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        if r["sub_avg"] is not None:
            by[r["station_id"]].append(r)
    out = {}
    for sid, subs in by.items():
        top = max(s["sub_avg"] for s in subs)
        out[sid] = {
            "source": "cpcb", "standard": "in_cpcb_naqi", "value": int(round(top)),
            "category": {"key": (c := cpcb.category_for(round(top))).key, "label": c.label, "color": c.color, "level": c.level},
            "dominant": sorted(s["pollutant"] for s in subs if s["sub_avg"] == top),
            "reported_at": max(s["reported_at"] for s in subs),
            "sub_indices": {s["pollutant"]: s["sub_avg"] for s in subs},
            "note": "As published by CPCB (data.gov.in); not recomputed by AirAtlas.",
        }
    return out


def stations_in_region(region_id: int, include_modeled: bool) -> list[dict]:
    return db.fetch(f"""select {STATION_COLS} from stations s join regions g on g.id = s.region_id
                        left join admin_areas a on a.id = s.admin_area_id
                        where s.region_id = %s and s.active and (%s or s.kind <> 'modeled') order by s.id""",
                    (region_id, include_modeled))


def latest(region_code: str, scale: str, include_modeled: bool = True) -> dict:
    region = region_row(region_code)
    std = resolve_scale(region_code, scale)
    now = datetime.now(timezone.utc)
    stations = stations_in_region(region["id"], include_modeled)
    ids = [s["id"] for s in stations]
    rows = readings_for(ids, HISTORY_HOURS)
    official = official_for(ids) if region["country_code"] == "IN" else {}
    out_stations = []
    by_area: dict[int, list[dict]] = defaultdict(list)
    for s in stations:
        entry = {**s, **evaluate_station(std, rows.get(s["id"], []), s["kind"], now, detail=False),
                 "official": official.get(s["id"])}
        out_stations.append(entry)
        if s["area_id"] is not None:
            by_area[s["area_id"]].append(entry)
    areas = []
    for area_id, entries in by_area.items():
        summary = summarize_area(entries)
        if summary:
            cat = std.category_for(summary["value"])
            summary["category"] = {"key": cat.key, "label": cat.label, "color": cat.color, "level": cat.level}
        areas.append({"area_id": area_id, "name": entries[0]["area"], **(summary or {"value": None, "basis": None, "n_stations": 0})})
    return {
        "region": {k: region[k] for k in ("code", "name", "timezone", "local_standard")},
        "scale": scale, "standard": std.code, "generated_at": now,
        "stations": out_stations, "areas": sorted(areas, key=lambda a: a["name"]),
    }


def station(station_id: int) -> dict:
    row = db.fetch_one(f"""select {STATION_COLS}, s.first_seen_at, s.last_seen_at
                           from stations s join regions g on g.id = s.region_id
                           left join admin_areas a on a.id = s.admin_area_id where s.id = %s""", (station_id,))
    if row is None:
        raise HTTPException(404, f"unknown station {station_id}")
    row["sources"] = db.fetch("""select src.code, src.name, src.kind, coalesce(ss.license, src.license) as license, src.attribution
                                 from station_sources ss join sources src on src.id = ss.source_id
                                 where ss.station_id = %s order by src.priority desc""", (station_id,))
    return row


def station_now(station_id: int) -> dict:
    """Latest AQI on the local standard and on every common scale, with health advice."""
    st = station(station_id)
    rows = readings_for([station_id], HISTORY_HOURS).get(station_id, [])
    now = datetime.now(timezone.utc)
    scales = {}
    for scale in ("local", *COMMON_SCALES):
        std = standard_for(st["region"], scale)
        ev = evaluate_station(std, rows, st["kind"], now)
        if ev["aqi"] and ev["aqi"]["category"]:
            cat = std.categories[ev["aqi"]["category"]["level"] - 1]
            ev["aqi"]["health"] = {"general": cat.health, "sensitive": cat.health_sensitive}
        scales[scale] = ev
    official = official_for([station_id]).get(station_id) if st["region"] in ("tamil_nadu", "kerala") else None
    return {**st, "now": scales, "official": official}


RANGES = {"24h": (timedelta(hours=24), "hourly"), "7d": (timedelta(days=7), "hourly"),
          "30d": (timedelta(days=30), "hourly"), "1y": (timedelta(days=365), "daily")}


def series(station_id: int, rng: str, scale: str) -> dict:
    from .evaluate import aqi_series  # local import keeps module import cheap

    if rng not in RANGES:
        raise HTTPException(422, f"range must be one of {list(RANGES)}")
    st = station(station_id)
    span, resolution = RANGES[rng]
    since = datetime.now(timezone.utc) - span
    out = {"station": {k: st[k] for k in ("id", "name", "region", "kind")}, "range": rng, "resolution": resolution,
           "since": since}
    if resolution == "hourly":
        hours = int(span.total_seconds() // 3600) + HISTORY_HOURS
        rows = readings_for([station_id], hours).get(station_id, [])
        out["points"] = [{k: r[k] for k in r if k != "station_id" and r[k] is not None} for r in rows if r["ts"] >= since]
        if rng in ("24h", "7d"):  # hourly AQI needs look-back history; 30 d of it would be slow and noisy
            std = resolve_scale(st["region"], scale)
            out["standard"] = std.code
            out["aqi"] = aqi_series(std, rows, since)
    else:
        out["points"] = db.fetch("""select day, n_hours, pm25_mean, pm25_max, pm10_mean, pm10_max, no2_mean, o3_mean, o3_max,
                                           so2_mean, co_mean, nh3_mean, dust_mean
                                    from readings_daily where station_id = %s and day >= %s order by day""",
                                 (station_id, since.date()))
    return out


def nearest(lat: float, lon: float, limit: int) -> list[dict]:
    rows = db.fetch(f"""select {STATION_COLS},
                               round((st_distance(s.geom::geography, p.g::geography) / 1000)::numeric, 1)::float8 as distance_km
                        from stations s join regions g on g.id = s.region_id left join admin_areas a on a.id = s.admin_area_id,
                             (select st_setsrid(st_makepoint(%(lon)s, %(lat)s), 4326) g) p
                        where s.active and s.kind <> 'modeled'
                        order by s.geom <-> p.g limit %(limit)s""", {"lat": lat, "lon": lon, "limit": limit})
    data = readings_for([r["id"] for r in rows], HISTORY_HOURS)
    now = datetime.now(timezone.utc)
    return [{**r, **evaluate_station(get_standard(LOCAL_STANDARD[r["region"]]), data.get(r["id"], []), r["kind"], now)}
            for r in rows]


def search(q: str) -> list[dict]:
    pattern = f"%{q.strip()}%"
    return db.fetch("""(select 'station' as type, s.id, s.name, coalesce(s.city, a.name) as context, g.code as region,
                               st_y(s.geom) as lat, st_x(s.geom) as lon
                        from stations s join regions g on g.id = s.region_id left join admin_areas a on a.id = s.admin_area_id
                        where s.active and s.kind <> 'modeled'
                          and (unaccent(s.name) ilike unaccent(%(p)s) or unaccent(coalesce(s.city, '')) ilike unaccent(%(p)s))
                        order by s.name limit 15)
                       union all
                       (select 'area', a.id, a.name, a.level, g.code, st_y(st_pointonsurface(a.geom)), st_x(st_pointonsurface(a.geom))
                        from admin_areas a join regions g on g.id = a.region_id
                        where unaccent(a.name) ilike unaccent(%(p)s) order by a.name limit 10)""", {"p": pattern})


def boundaries(region_code: str) -> dict:
    region = region_row(region_code)
    rows = db.fetch("""select id, name, level,
                              st_asgeojson(st_simplifypreservetopology(geom, 0.005), 4)::json as geometry
                       from admin_areas where region_id = %s order by name""", (region["id"],))
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": r["id"], "properties": {"id": r["id"], "name": r["name"], "level": r["level"]},
         "geometry": r["geometry"]} for r in rows]}


def compare(scale: str) -> dict:
    if scale not in COMMON_SCALES:
        raise HTTPException(422, f"comparisons use a common scale: {list(COMMON_SCALES)}")
    now_by_region = {}
    for code in LOCAL_STANDARD:
        snap = latest(code, scale, include_modeled=False)
        ranked = sorted((a for a in snap["areas"] if a["value"] is not None), key=lambda a: a["value"])
        featured = next((a for a in snap["areas"] if a["name"] == FEATURED_AREAS[code]), None)
        usable = [s for s in snap["stations"] if s["aqi"] and s["aqi"]["value"] is not None]
        now_by_region[code] = {
            "featured_area": featured, "best_areas": ranked[:3], "worst_areas": ranked[::-1][:3],
            "stations_with_data": len(usable), "stations_total": len(snap["stations"]),
        }
    monthly = db.fetch("""select g.code as region, a.name as area, date_trunc('month', d.day)::date as month,
                                 round(avg(d.pm25_mean)::numeric, 1)::float8 as pm25, count(distinct d.station_id) as stations,
                                 count(*) as station_days
                          from readings_daily d join stations s on s.id = d.station_id and s.kind <> 'modeled'
                          join regions g on g.id = s.region_id left join admin_areas a on a.id = s.admin_area_id
                          where d.day >= (current_date - interval '12 months') and d.pm25_mean is not null
                            and (d.n_hours is null or d.n_hours >= 18)
                          group by grouping sets ((g.code, month), (g.code, a.name, month))
                          order by region, area nulls first, month""")
    featured = {(r, a) for r, a in FEATURED_AREAS.items()}
    return {
        "scale": scale, "generated_at": datetime.now(timezone.utc), "now": now_by_region,
        "monthly_pm25": {
            "who_annual_guideline": 5.0,
            "regions": [m for m in monthly if m["area"] is None],
            "featured_areas": [m for m in monthly if (m["region"], m["area"]) in featured],
        },
    }


def status() -> dict:
    runs = db.fetch("""select region, source,
                              max(finished_at) filter (where status in ('success', 'partial')) as last_success,
                              (array_agg(status order by started_at desc))[1] as last_status,
                              (array_agg(error order by started_at desc))[1] as last_error,
                              count(*) filter (where status = 'failed' and started_at > now() - interval '24 hours') as failures_24h,
                              coalesce(sum(rows_written) filter (where started_at > now() - interval '24 hours'), 0) as rows_24h
                       from ingestion_runs where job in ('hourly', 'modeled')
                       group by region, source order by region, source""")
    freshness = db.fetch("""select g.code as region, src.code as source, max(r.ts) as newest
                            from readings r join stations s on s.id = r.station_id join regions g on g.id = s.region_id
                            join sources src on src.id = r.source_id where r.ts > now() - interval '7 days'
                            group by 1, 2 order by 1, 2""")
    official = db.fetch("""select g.code as region, max(o.reported_at) as newest from official_aqi o
                           join stations s on s.id = o.station_id join regions g on g.id = s.region_id group by 1""")
    maint = db.fetch_one("""select finished_at, status, details->'storage_bytes' as storage_bytes, details->'dropped_partitions' as dropped
                            from ingestion_runs where job = 'maintenance' order by started_at desc limit 1""")
    size = db.fetch_one("select pg_database_size(current_database()) as bytes")["bytes"]
    limit = 1024**3
    return {"generated_at": datetime.now(timezone.utc), "runs": runs, "freshness": freshness, "official_freshness": official,
            "maintenance": maint, "storage": {"bytes": size, "limit_bytes": limit, "used_pct": round(100 * size / limit, 1),
                                              "plan": "Neon free (1 GB per project)"}}
