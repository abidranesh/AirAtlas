"""AirAtlas read API. Interactive docs at /api/docs."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal

from airatlas_aqi import COMMON_SCALES, STANDARDS, get_standard
from fastapi import APIRouter, FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from . import caching, data, db, heatmap
from .caching import Policy

Scale = Literal["local", "eu_eaqi", "who_2021_pm25"]
Region = Literal["tamil_nadu", "kerala", "uae", "germany"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    db.close()


app = FastAPI(title="AirAtlas API", version="1.0", lifespan=lifespan, docs_url="/api/docs",
              openapi_url="/api/openapi.json", redoc_url=None,
              description="Air quality for Tamil Nadu, Kerala, the UAE and Germany. AQI is computed at read time "
                          "from stored raw concentrations. Data unavailable is reported as such, never filled in.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])
v1 = APIRouter(prefix="/api/v1")


@v1.get("/health", summary="Liveness and database round trip")
def health(response: Response):
    caching.apply(response, Policy.NONE)
    return {"ok": True, "db_time": db.fetch_one("select now() as t")["t"]}


@v1.get("/meta", summary="Regions, AQI standards (categories, colours, health advice) and source attribution")
def meta(response: Response):
    caching.apply(response, Policy.DAILY)
    standards = {}
    for code in STANDARDS:
        std = get_standard(code)
        s = std.spec
        standards[code] = {
            "name": s["name"], "short_name": s["short_name"], "scale": s["scale"], "version": s["version"],
            "categories": [{"key": c.key, "label": c.label, "color": c.color, "level": c.level,
                            "index_range": c.index_range, "health": c.health, "health_sensitive": c.health_sensitive}
                           for c in std.categories],
            "sources": s["sources"],
        }
    return {"regions": data.regions(), "standards": standards, "common_scales": list(COMMON_SCALES),
            "sources": db.fetch("select code, name, kind, license, attribution, url from sources order by priority desc")}


@v1.get("/regions/{region}/latest", summary="Latest AQI for every station and admin area in a region")
def region_latest(response: Response, region: Region, scale: Scale = "local", include_modeled: bool = True):
    caching.apply(response, Policy.LIVE)
    return data.latest(region, scale, include_modeled)


@v1.get("/regions/{region}/boundaries", summary="Admin boundaries (simplified GeoJSON)")
def region_boundaries(response: Response, region: Region):
    caching.apply(response, Policy.STATIC)
    return data.boundaries(region)


@v1.get("/regions/{region}/heatmap.png", summary="Interpolated PM2.5 (IDW) as a PNG overlay covering the region's bbox",
        response_class=Response, responses={200: {"content": {"image/png": {}}}})
def region_heatmap(region: Region, scale: Scale = "local"):
    png, info = heatmap.build(region, scale)
    return Response(png, media_type="image/png", headers={
        "Cache-Control": caching.header(Policy.LIVE),
        # Diagnostics for the UI and for tests; the image itself carries no metadata.
        "X-Heatmap-Info": ";".join(f"{k}={v}" for k, v in info.items()),
        "Access-Control-Expose-Headers": "X-Heatmap-Info",
    })


@v1.get("/stations/{station_id}", summary="Station details with AQI on the local standard and all common scales")
def station_detail(response: Response, station_id: int):
    caching.apply(response, Policy.LIVE)
    return data.station_now(station_id)


@v1.get("/stations/{station_id}/series", summary="Concentration trends (hourly up to 30 d, daily for 1 y) and hourly AQI (24 h / 7 d)")
def station_series(response: Response, station_id: int, range: Literal["24h", "7d", "30d", "1y"] = "24h", scale: Scale = "local"):
    caching.apply(response, Policy.LIVE)
    return data.series(station_id, range, scale)


@v1.get("/nearest", summary="Nearest measured stations to a point (round coordinates client-side for cache hits)")
def nearest(response: Response, lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180),
            limit: int = Query(3, ge=1, le=10)):
    caching.apply(response, Policy.LIVE)
    return {"stations": data.nearest(round(lat, 2), round(lon, 2), limit)}


@v1.get("/search", summary="Stations and admin areas by name (accent-insensitive)")
def search(response: Response, q: str = Query(min_length=2, max_length=60)):
    caching.apply(response, Policy.DAILY)
    return {"results": data.search(q)}


@v1.get("/compare", summary="Cross-region comparison on a common scale, with monthly PM2.5")
def compare(response: Response, scale: Literal["eu_eaqi", "who_2021_pm25"] = "eu_eaqi"):
    caching.apply(response, Policy.LIVE)
    return data.compare(scale)


@v1.get("/status", summary="Ingestion health per region and source, data freshness and storage use")
def status(response: Response):
    caching.apply(response, Policy.STATUS)
    return data.status()


app.include_router(v1)
