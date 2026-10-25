import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.db
H = timedelta(hours=1)


def test_detect_region_stores_episodes_with_hints_and_is_idempotent(pg):
    from airatlas_ingest import db
    from airatlas_ingest.config import REGIONS
    from airatlas_ingest.models import FireEvent, Reading, StationIn, StationKey, WeatherObs

    from airatlas_ml.job import detect_region

    conn = pg
    db.ensure_partitions(conn)
    conn.execute("""insert into admin_areas (region_id, level, name, source, geom)
                    values (1, 'district', 'Chennai', 'test', st_multi(st_makeenvelope(80.0, 12.8, 80.4, 13.3, 4326)))""")
    db.upsert_stations(conn, "openaq", [StationIn(source="openaq", external_id="m1", name="Monitor", lat=13.08, lon=80.27, kind="reference")])
    db.upsert_stations(conn, "open_meteo", [StationIn(source="open_meteo", external_id="p1", name="Point", lat=13.05, lon=80.2, kind="modeled")])

    now = datetime.now(timezone.utc).replace(minute=30, second=0, microsecond=0) - 2 * H
    start = now - 14 * 24 * H
    spike_at = now - 30 * H
    mon, pt = StationKey(source="openaq", external_id="m1"), StationKey(source="open_meteo", external_id="p1")
    readings, weather = [], []
    t = start
    while t <= now:
        v = 20 + 10 * max(0.0, math.cos(2 * math.pi * (t.hour - 18) / 24))
        if spike_at <= t < spike_at + 3 * H:
            v = 160.0
        readings.append(Reading(station=mon, ts=t, values={"pm25": v}))
        weather.append(WeatherObs(station=pt, ts=t, wind_dir_deg=270, wind_ms=3.0, precip_mm=0.0))
        t += H
    rej = Counter()
    db.write_readings(conn, "openaq", readings, rej)
    db.write_weather(conn, weather, rej)
    db.write_fires(conn, [FireEvent(region_id=1, detected_at=spike_at - 6 * H, lat=13.08, lon=79.7 + i * 0.01, frp=15.0,
                                    satellite="N", daynight="D") for i in range(6)])

    result = detect_region(conn, REGIONS["tamil_nadu"], days=10, now=now)
    assert result["episodes"] == 1 and result["hint_kinds"].get("fire_upwind") == 1
    row = conn.execute("select pollutant, value, starts_at, ends_at, cause_hints, details from anomalies").fetchone()
    pollutant, value, starts, ends, hints, details = row
    assert pollutant == "pm25" and value == 160 and ends - starts == 2 * H and details["hours"] == 3
    assert hints[0]["kind"] == "fire_upwind" and hints[0]["confidence"] == "high"

    again = detect_region(conn, REGIONS["tamil_nadu"], days=10, now=now)   # re-run: replace, never duplicate
    assert again["episodes"] == 1 and again["replaced"] == 1
    assert conn.execute("select count(*) from anomalies").fetchone()[0] == 1
    assert json.dumps(hints)  # stored hints are plain JSON
