"""Endpoint tests against a seeded throwaway schema (CI: PostGIS service container)."""

from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.db
UTC = timezone.utc


@pytest.fixture(scope="module")
def client(schema_url):
    from airatlas_ingest import db as idb
    from airatlas_ingest.models import OfficialSubIndex, Reading, StationIn, StationKey
    from fastapi.testclient import TestClient

    conn, url, schema = schema_url
    idb.ensure_partitions(conn)
    conn.execute("""insert into admin_areas (region_id, level, name, source, geom) values
        (4, 'state', 'Berlin', 'test', st_multi(st_makeenvelope(13.08, 52.33, 13.77, 52.68, 4326))),
        (4, 'state', 'Sachsen', 'test', st_multi(st_makeenvelope(11.8, 50.2, 15.0, 51.7, 4326))),
        (1, 'district', 'Chennai', 'test', st_multi(st_makeenvelope(80.10, 12.85, 80.30, 13.25, 4326)))""")
    S = lambda src, ext, name, lat, lon, kind="reference": StationIn(source=src, external_id=ext, name=name, lat=lat, lon=lon, kind=kind)
    idb.upsert_stations(conn, "uba", [S("uba", "DEBE010", "Berlin Wedding", 52.543, 13.349),
                                      S("uba", "DESN001", "Görlitz", 51.155, 14.988),
                                      S("uba", "DEBE999", "Berlin Old", 52.50, 13.40)])
    idb.upsert_stations(conn, "open_meteo", [S("open_meteo", "germany:Berlin", "Berlin (model)", 52.5, 13.4, "modeled")])
    idb.upsert_stations(conn, "cpcb", [S("cpcb", "Velachery", "Velachery Res. Area, Chennai - CPCB", 12.99, 80.22)])
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    rej = Counter()
    idb.write_readings(conn, "uba", [
        Reading(station=StationKey(source="uba", external_id="DEBE010"), ts=now - timedelta(hours=h + 2),
                values={"pm25": 12.0 + h % 3, "no2": 45.0, "o3": 30.0, "pm10": 20.0}) for h in range(30)] + [
        Reading(station=StationKey(source="uba", external_id="DESN001"), ts=now - timedelta(hours=h + 2),
                values={"pm25": 4.0, "no2": 8.0}) for h in range(30)] + [
        Reading(station=StationKey(source="uba", external_id="DEBE999"), ts=now - timedelta(hours=30), values={"pm25": 400.0})],
        rej)
    idb.write_readings(conn, "open_meteo", [Reading(station=StationKey(source="open_meteo", external_id="germany:Berlin"),
                                                    ts=now - timedelta(hours=h), values={"pm25": 5.0}) for h in range(5)], rej)
    idb.write_official(conn, [OfficialSubIndex(station=StationKey(source="cpcb", external_id="Velachery"), reported_at=now - timedelta(hours=1),
                                               pollutant=p, sub_avg=v) for p, v in (("pm25", 87.0), ("no2", 20.0), ("co", 31.0))], rej)
    for day in range(1, 40):
        conn.execute("""insert into readings_daily (station_id, day, source_id, n_hours, pm25_mean)
                        select station_id, current_date - %s, 2, 24, 10 + mod(%s, 5) from station_sources where external_id = 'DEBE010'""", (day, day))
    with idb.tracked_run(conn, "hourly", "germany", "uba") as run:
        run.written = 61

    from airatlas_api import db as api_db
    api_db.close()
    api_db.init(url, search_path=f"{schema}, public")
    from app import app
    yield TestClient(app)
    api_db.close()


def sid(client, name):
    return next(r["id"] for r in client.get("/api/v1/search", params={"q": name}).json()["results"] if r["type"] == "station")


def test_health_is_not_cached(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"


def test_meta_lists_regions_standards_and_sources(client):
    d = client.get("/api/v1/meta").json()
    assert [r["code"] for r in d["regions"]] == ["tamil_nadu", "kerala", "uae", "germany"]
    assert set(d["standards"]) >= {"in_cpcb_naqi", "de_uba_lqi", "eu_eaqi", "ae_eaqi", "who_2021_pm25"}
    assert any(s["code"] == "uba" and "Umweltbundesamt" in s["attribution"] for s in d["sources"])


def test_region_latest_local_scale(client):
    r = client.get("/api/v1/regions/germany/latest")
    assert r.status_code == 200 and "s-maxage=" in r.headers["cache-control"]
    d = r.json()
    wedding = next(s for s in d["stations"] if s["name"] == "Berlin Wedding")
    assert wedding["freshness"] == "fresh" and wedding["aqi"]["category"]["key"] == "moderate"  # NO2 45 -> UBA class 3
    assert "sub_indices" not in wedding["aqi"]
    old = next(s for s in d["stations"] if s["name"] == "Berlin Old")
    assert old["freshness"] == "unavailable" and old["aqi"] is None  # 400 ug/m3 from 30 h ago is never shown as current
    berlin = next(a for a in d["areas"] if a["name"] == "Berlin")
    assert berlin["basis"] == "measured" and berlin["n_stations"] == 1  # the model point does not dilute measurements


def test_region_latest_common_scale(client):
    d = client.get("/api/v1/regions/germany/latest", params={"scale": "eu_eaqi"}).json()
    assert d["standard"] == "eu_eaqi"
    wedding = next(s for s in d["stations"] if s["name"] == "Berlin Wedding")
    assert wedding["aqi"]["category"]["key"] == "moderate"  # NO2 45 is EEA 'moderate' (26-60)


def test_bad_inputs(client):
    assert client.get("/api/v1/regions/germany/latest", params={"scale": "us_aqi"}).status_code == 422
    assert client.get("/api/v1/regions/atlantis/latest").status_code == 422
    assert client.get("/api/v1/stations/999999").status_code == 404


def test_india_shows_official_cpcb_index_without_inventing_concentrations(client):
    d = client.get("/api/v1/regions/tamil_nadu/latest").json()
    v = next(s for s in d["stations"] if s["name"].startswith("Velachery"))
    assert v["official"]["value"] == 87 and v["official"]["category"]["key"] == "satisfactory"
    assert v["official"]["dominant"] == ["pm25"]
    assert v["aqi"] is None and v["freshness"] == "unavailable"


def test_station_detail_has_every_scale_and_health_advice(client):
    d = client.get(f"/api/v1/stations/{sid(client, 'Wedding')}").json()
    assert set(d["now"]) == {"local", "eu_eaqi", "who_2021_pm25"}
    assert d["now"]["local"]["aqi"]["health"]["general"]
    assert d["now"]["who_2021_pm25"]["aqi"]["extra"]["who_multiple"] == pytest.approx(13 / 15, abs=0.05)
    assert d["sources"][0]["code"] == "uba"


def test_series_hourly_with_aqi_and_daily(client):
    s = sid(client, "Wedding")
    day = client.get(f"/api/v1/stations/{s}/series", params={"range": "24h"}).json()
    # 22 or 23 hourly points fall inside "the last 24 h" depending on the current minute
    assert day["resolution"] == "hourly" and len(day["points"]) in (22, 23)
    assert [a["ts"] for a in day["aqi"]] == [p["ts"] for p in day["points"]]
    year = client.get(f"/api/v1/stations/{s}/series", params={"range": "1y"}).json()
    assert year["resolution"] == "daily" and len(year["points"]) == 39


def test_nearest_and_accent_insensitive_search(client):
    near = client.get("/api/v1/nearest", params={"lat": 52.54, "lon": 13.35}).json()["stations"]
    assert near[0]["name"] == "Berlin Wedding" and near[0]["distance_km"] < 1
    assert all(s["kind"] != "modeled" for s in near)
    names = [r["name"] for r in client.get("/api/v1/search", params={"q": "gorlitz"}).json()["results"]]
    assert "Görlitz" in names


def test_boundaries_geojson(client):
    d = client.get("/api/v1/regions/germany/boundaries").json()
    assert d["type"] == "FeatureCollection" and {f["properties"]["name"] for f in d["features"]} == {"Berlin", "Sachsen"}


def test_compare_requires_common_scale(client):
    assert client.get("/api/v1/compare", params={"scale": "local"}).status_code == 422
    d = client.get("/api/v1/compare", params={"scale": "eu_eaqi"}).json()
    assert d["now"]["germany"]["featured_area"]["name"] == "Berlin"
    months = [m for m in d["monthly_pm25"]["featured_areas"] if m["region"] == "germany"]
    assert months and all(m["area"] == "Berlin" for m in months)


def test_status_reports_runs_freshness_and_storage(client):
    d = client.get("/api/v1/status").json()
    run = next(r for r in d["runs"] if r["source"] == "uba")
    assert run["last_status"] == "success" and run["rows_24h"] == 61
    assert d["storage"]["limit_bytes"] == 1024**3 and d["storage"]["used_pct"] >= 0


def test_heatmap_png(client):
    from test_idw import decode

    r = client.get("/api/v1/regions/germany/heatmap.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert "s-maxage=" in r.headers["cache-control"]
    info = dict(kv.split("=", 1) for kv in r.headers["x-heatmap-info"].split(";"))
    assert info["standard"] == "de_uba_lqi" and info["pollutant"] == "pm25/1h"
    assert int(info["measured_points"]) >= 1   # the 30-h-old 'Berlin Old' station must not count
    img = decode(r.content)
    w, h = map(int, info["size"].split("x"))
    assert img.shape == (h, w, 4)
    opaque = img[img[..., 3] > 0]
    assert len(opaque) > 0 and (img[..., 3] == 0).any()   # coloured near data, transparent elsewhere
