"""Admin boundaries (geoBoundaries, open licences) and the modeled grid points derived from them."""

from __future__ import annotations

import json
import unicodedata
from collections import Counter

import psycopg

from . import db, logs
from .config import Region
from .http import HttpClient
from .models import StationIn, validate_all

log = logs.get(__name__)
API = "https://www.geoboundaries.org/api/current/gbOpen/{iso3}/{adm}/"


def _plain(name: str) -> str:
    """'Tamil Nādu' -> 'tamil nadu' (geoBoundaries uses IAST diacritics)."""
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().casefold()


def _layer(http: HttpClient, iso3: str, adm: str) -> tuple[dict, dict]:
    meta = http.get_json(API.format(iso3=iso3, adm=adm))
    geojson = http.get_json(meta["simplifiedGeometryGeoJSON"])
    return meta, geojson


def load(conn: psycopg.Connection, region: Region, http: HttpClient | None = None) -> int:
    """Load (or refresh) the region's admin areas. Returns the number of areas stored."""
    http = http or HttpClient("geoboundaries", per_minute=20)
    spec = region.boundary
    meta, layer = _layer(http, spec.iso3, spec.adm)
    source = f"geoBoundaries {spec.iso3} {spec.adm} {meta['boundaryYearRepresented']} ({meta['boundaryLicense']})"
    with conn.transaction():
        conn.execute("create temp table _ab (name text, geom geometry) on commit drop")
        # One statement for all features: PostGIS parses the GeoJSON server-side.
        conn.execute(
            """insert into _ab (name, geom)
               select f->'properties'->>'shapeName', st_multi(st_collectionextract(st_makevalid(st_setsrid(st_geomfromgeojson(f->>'geometry'), 4326)), 3))
               from jsonb_array_elements(%s::jsonb) f""",
            (json.dumps(layer["features"]),),
        )
        if spec.within_iso3_adm1:
            _, parents = _layer(http, spec.iso3, "ADM1")
            parent = next(f for f in parents["features"] if _plain(f["properties"]["shapeName"]) == _plain(spec.within_iso3_adm1))
            conn.execute(
                "delete from _ab where not st_within(st_pointonsurface(geom), st_makevalid(st_setsrid(st_geomfromgeojson(%s), 4326)))",
                (json.dumps(parent["geometry"]),),
            )
        n = conn.execute(
            """insert into admin_areas (region_id, level, name, source, geom)
               select %s, %s, name, %s, st_union(geom)::geometry(MultiPolygon, 4326) from _ab group by name
               on conflict (region_id, level, name) do update set geom = excluded.geom, source = excluded.source""",
            (region.id, spec.level, source),
        ).rowcount
        # Stations seen before the boundaries existed get their region now.
        conn.execute("""update stations s set (admin_area_id, region_id) = (
                            select a.id, a.region_id from admin_areas a
                            where a.geom && st_expand(s.geom, 0.05) and st_dwithin(a.geom::geography, s.geom::geography, 5000)
                            order by st_distance(a.geom::geography, s.geom::geography) limit 1)
                        where s.admin_area_id is null""")
    log.info("boundaries loaded", region=region.code, areas=n, source=source)
    return n


def model_points(conn: psycopg.Connection, region: Region) -> list[StationIn]:
    """One modeled point per admin area (point on surface), plus a regular grid for sparse regions."""
    rows = conn.execute(
        "select name, st_y(p), st_x(p) from (select name, st_pointonsurface(geom) p from admin_areas where region_id = %s) a",
        (region.id,),
    ).fetchall()
    raws = [{"source": "open_meteo", "external_id": f"{region.code}:{name}", "name": f"{name} (model)",
             "lat": lat, "lon": lon, "kind": "modeled", "license": "CC BY 4.0"} for name, lat, lon in rows]
    if region.model_grid_deg:
        w, s, e, n = region.bbox
        step = region.model_grid_deg
        grid = [(round(s + i * step, 3), round(w + j * step, 3))
                for i in range(int((n - s) / step) + 1) for j in range(int((e - w) / step) + 1)]
        inside = conn.execute(
            """select g.lat, g.lon from unnest(%s::float8[], %s::float8[]) g(lat, lon)
               where exists (select 1 from admin_areas a where a.region_id = %s
                             and st_intersects(a.geom, st_setsrid(st_makepoint(g.lon, g.lat), 4326)))""",
            ([g[0] for g in grid], [g[1] for g in grid], region.id),
        ).fetchall()
        raws += [{"source": "open_meteo", "external_id": f"{region.code}:grid:{lat:.3f},{lon:.3f}",
                  "name": f"Grid {lat:.2f}N {lon:.2f}E (model)", "lat": lat, "lon": lon, "kind": "modeled",
                  "license": "CC BY 4.0"} for lat, lon in inside]
    return validate_all(StationIn, raws, Counter())


def ensure_model_points(conn: psycopg.Connection, region: Region) -> int:
    points = model_points(conn, region)
    db.upsert_stations(conn, "open_meteo", points)
    return len(points)
