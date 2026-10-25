"""Interpolated PM2.5 heatmap per region, coloured on the selected AQI standard.

Per station, PM2.5 is taken exactly as the standard consumes it (24-h mean for CPCB, UAE and WHO;
1-h for UBA and the EEA index) via the engine's own averaging rules, interpolated with IDW, and each
cell is classified by the engine, so the overlay can never disagree with the station markers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

import numpy as np
from airatlas_aqi import AqiStandard, Pollutant

from . import data, db
from .evaluate import HISTORY_HOURS, freshness, series_by_pollutant
from .idw import Grid, encode_png, hex_rgb, idw

# cell size and search radius per region: denser networks get finer cells; the UAE's sparse
# sensors and 0.75 degree model grid need a wider radius.
GRID = {"tamil_nadu": (4.0, 60.0), "kerala": (3.0, 50.0), "uae": (5.0, 100.0), "germany": (5.0, 60.0)}
TRUST = {"reference": 1.0, "low_cost": 0.6, "modeled": 0.25}
ALPHA = 150


@lru_cache(maxsize=16)
def region_mask(region_id: int, grid: Grid) -> np.ndarray:
    """Cells inside the region's admin boundaries (buffered ~2 km for simplified coastlines)."""
    lat, lon = grid.centres()
    row = db.fetch_one(
        """with u as (select st_buffer(st_union(st_simplifypreservetopology(geom, 0.01)), 0.02) as g
                      from admin_areas where region_id = %(r)s)
           select array_agg(st_intersects(u.g, st_setsrid(st_makepoint(c.lon, c.lat), 4326)) order by c.i) as inside
           from u, unnest(%(lat)s::float8[], %(lon)s::float8[]) with ordinality as c(lat, lon, i)""",
        {"r": region_id, "lat": lat.tolist(), "lon": lon.tolist()},
    )
    return np.array(row["inside"] or [False] * lat.size, dtype=bool)


def station_points(std: AqiStandard, stations: list[dict], rows: dict[int, list[dict]], now: datetime):
    """(lat, lon, pm25-as-the-standard-averages-it, trust) for every station with usable data."""
    key = next(k for k in std.inputs() if k[0] is Pollutant.PM25)
    pts = []
    for s in stations:
        r = rows.get(s["id"])
        if not r:
            continue
        latest = max(x["ts"] for x in r)
        if freshness(latest, s["kind"], now) == "unavailable":
            continue
        v = std.from_hourly(series_by_pollutant(r), latest).get(key)
        if v is not None:
            pts.append((s["lat"], s["lon"], v, TRUST[s["kind"]], s["kind"]))
    return key, pts


def colourize(std: AqiStandard, key, values: np.ndarray) -> np.ndarray:
    """RGBA per cell. Classification goes through the engine on each distinct value (rounded to
    0.1 ug/m3), which keeps every standard's rounding/truncation rules without re-implementing them."""
    rgba = np.zeros((values.size, 4), np.uint8)
    ok = ~np.isnan(values)
    rounded = np.round(values[ok], 1)
    uniq, inverse = np.unique(rounded, return_inverse=True)
    palette = np.zeros((uniq.size, 4), np.uint8)
    for i, u in enumerate(uniq):
        subs = std.sub_indices({key: float(u)})
        if subs:
            palette[i] = (*hex_rgb(subs[0].category.color), ALPHA)
    rgba[ok] = palette[inverse]
    return rgba


def build(region_code: str, scale: str) -> tuple[bytes, dict]:
    region = data.region_row(region_code)
    std = data.resolve_scale(region_code, scale)
    ring = region["bbox"]["coordinates"][0]
    west, east = min(p[0] for p in ring), max(p[0] for p in ring)
    south, north = min(p[1] for p in ring), max(p[1] for p in ring)
    cell_km, radius_km = GRID[region_code]
    grid = Grid.for_bbox(west, south, east, north, cell_km)

    stations = data.stations_in_region(region["id"], include_modeled=True)
    rows = data.readings_for([s["id"] for s in stations], HISTORY_HOURS)
    key, pts = station_points(std, stations, rows, datetime.now(timezone.utc))

    lat, lon = grid.centres()
    mask = region_mask(region["id"], grid)
    values = np.full(lat.size, np.nan)
    if pts:
        p = np.array([x[:4] for x in pts], dtype=float)
        values[mask] = idw(lat[mask], lon[mask], p[:, 0], p[:, 1], p[:, 2], p[:, 3], radius_km=radius_km)
    rgba = colourize(std, key, values).reshape(grid.height, grid.width, 4)
    info = {
        "standard": std.code, "pollutant": f"pm25/{key[1].value}",
        "points": len(pts), "measured_points": sum(1 for x in pts if x[4] != "modeled"),
        "cells": int(mask.sum()), "cells_coloured": int((~np.isnan(values)).sum()),
        "size": f"{grid.width}x{grid.height}",
    }
    return encode_png(rgba), info
