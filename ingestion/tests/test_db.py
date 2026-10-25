"""Integration tests against real Postgres + PostGIS (CI: service container; locally: TEST_DATABASE_URL)."""

from collections import Counter
from datetime import date, datetime, timedelta, timezone

import pytest

from airatlas_ingest import db, jobs
from airatlas_ingest.models import Reading, StationIn, StationKey

pytestmark = pytest.mark.db
UTC = timezone.utc
CHENNAI_BOX = "st_multi(st_makeenvelope(80.10, 12.85, 80.30, 13.25, 4326))"


@pytest.fixture(scope="module")
def conn(pg):
    pg.execute(f"insert into admin_areas (region_id, level, name, source, geom) values (1, 'district', 'Chennai', 'test', {CHENNAI_BOX})")
    return pg


def station(source, ext, name, lat, lon, kind="reference"):
    return StationIn(source=source, external_id=ext, name=name, lat=lat, lon=lon, kind=kind)


def test_migrations_are_idempotent(conn):
    assert db.migrate(conn) == []


def test_same_monitor_from_two_sources_becomes_one_station(conn):
    a = db.upsert_stations(conn, "cpcb", [station("cpcb", "Velachery Res. Area, Chennai - CPCB", "Velachery Res. Area, Chennai - CPCB", 12.9925, 80.2205)])
    # OpenAQ's copy: same name, coordinates ~150 m off
    b = db.upsert_stations(conn, "openaq", [station("openaq", "5655", "Velachery Res. Area, Chennai - CPCB", 12.9937, 80.2214)])
    assert a["Velachery Res. Area, Chennai - CPCB"] == b["5655"]
    region = conn.execute("select region_id from stations where id = %s", (b["5655"],)).fetchone()[0]
    assert region == 1


def test_low_cost_sensor_next_to_a_monitor_stays_separate(conn):
    ids = db.upsert_stations(conn, "openaq", [station("openaq", "999", "Somebody's balcony", 12.9926, 80.2206, kind="low_cost")])
    ref = db.upsert_stations(conn, "cpcb", [station("cpcb", "Velachery Res. Area, Chennai - CPCB", "Velachery Res. Area, Chennai - CPCB", 12.9925, 80.2205)])
    assert ids["999"] != ref["Velachery Res. Area, Chennai - CPCB"]


def test_coastal_station_outside_simplified_polygon_still_gets_region(conn):
    ids = db.upsert_stations(conn, "openaq", [station("openaq", "777", "Beach", 13.05, 80.33)])  # ~3 km east of the box
    assert conn.execute("select region_id from stations where id = %s", (ids["777"],)).fetchone()[0] == 1


def test_far_away_station_gets_no_region(conn):
    ids = db.upsert_stations(conn, "openaq", [station("openaq", "888", "Bengaluru", 12.97, 77.59)])
    assert conn.execute("select region_id from stations where id = %s", (ids["888"],)).fetchone()[0] is None


def test_readings_merge_sensors_and_respect_source_priority(conn):
    db.ensure_partitions(conn)
    sid = db.upsert_stations(conn, "openaq", [station("openaq", "5655", "Velachery Res. Area, Chennai - CPCB", 12.9937, 80.2214)])["5655"]
    conn.execute("insert into station_sources (source_id, external_id, station_id) values (5, 'm1', %s), (3, 'e1', %s)", (sid, sid))
    ts = datetime.now(UTC).replace(minute=30, second=0, microsecond=0) - timedelta(hours=3)
    rej = Counter()
    oaq = StationKey(source="openaq", external_id="5655")
    # two sensors of one station-hour in one batch -> one row
    db.write_readings(conn, "openaq", [Reading(station=oaq, ts=ts, values={"pm25": 50}),
                                       Reading(station=oaq, ts=ts, values={"no2": 20})], rej)
    # a model (priority 10) must not overwrite measured data (priority 70)
    db.write_readings(conn, "open_meteo", [Reading(station=StationKey(source="open_meteo", external_id="m1"), ts=ts, values={"pm25": 5})], rej)
    # a higher-priority source wins, and its missing NO2 does not erase the existing value
    db.write_readings(conn, "eea", [Reading(station=StationKey(source="eea", external_id="e1"), ts=ts, values={"pm25": 48})], rej)
    row = conn.execute("select pm25, no2, source_id from readings where station_id = %s and ts = %s", (sid, ts)).fetchone()
    assert row == (48.0, 20.0, 3)
    db.write_readings(conn, "openaq", [Reading(station=StationKey(source="openaq", external_id="nope"), ts=ts, values={"pm25": 1})], rej)
    assert rej["unknown station"] == 1


def test_daily_aggregate_uses_local_calendar_day(conn):
    sid = db.upsert_stations(conn, "openaq", [station("openaq", "4242", "Local day test", 13.0, 80.2)])["4242"]
    key = StationKey(source="openaq", external_id="4242")
    day_start_utc = datetime.combine(date.today() - timedelta(days=1), datetime.min.time(), UTC) - timedelta(hours=5, minutes=30)
    rows = [Reading(station=key, ts=day_start_utc + timedelta(hours=h), values={"pm25": 10.0 + h}) for h in range(24)]
    db.write_readings(conn, "openaq", rows, Counter())
    jobs.aggregate_daily(conn, day_start_utc - timedelta(days=1))
    n, mean, mx = conn.execute("select n_hours, pm25_mean, pm25_max from readings_daily where station_id = %s and day = %s",
                               (sid, date.today() - timedelta(days=1))).fetchone()
    assert (n, mean, mx) == (24, pytest.approx(21.5), 33.0)


def test_retention_archives_held_hours_then_drops_old_partitions(conn):
    sid = db.upsert_stations(conn, "openaq", [station("openaq", "5150", "Archive test", 13.1, 80.25)])["5150"]
    old = (datetime.now(UTC) - timedelta(days=95)).replace(minute=30, second=0, microsecond=0)
    conn.execute("select ensure_weekly_partitions('readings', 16, 0)")
    db.write_readings(conn, "openaq", [Reading(station=StationKey(source="openaq", external_id="5150"), ts=old, values={"pm25": 300})], Counter())
    conn.execute("insert into retention_holds (label, region_id, starts_at, ends_at) values ('test', 1, %s, %s)",
                 (old - timedelta(hours=1), old + timedelta(hours=1)))
    conn.execute(jobs.ARCHIVE_HOLDS)
    dropped = [r[0] for r in conn.execute("select drop_old_partitions('readings', interval '90 days')")]
    assert dropped
    assert conn.execute("select count(*) from readings where station_id = %s", (sid,)).fetchone()[0] == 0
    assert conn.execute("select pm25 from readings_archive where station_id = %s", (sid,)).fetchone()[0] == 300


def test_failed_run_is_recorded(conn):
    with pytest.raises(RuntimeError):
        with db.tracked_run(conn, "hourly", "kerala", "cpcb") as run:
            run.fetched = 3
            raise RuntimeError("upstream exploded")
    status, error, fetched = conn.execute(
        "select status, error, rows_fetched from ingestion_runs order by id desc limit 1").fetchone()
    assert (status, fetched) == ("failed", 3) and "upstream exploded" in error


def test_run_status_is_recorded_after_the_connection_drops(conn):
    """Neon suspends idle compute and drops connections; the run log must still be written."""
    import os

    other = db.connect(os.environ["TEST_DATABASE_URL"])
    other.execute(f"set search_path to {conn.execute('show search_path').fetchone()[0]}")
    run = db.Run(other, "hourly", "kerala", "cpcb")
    run.fetched = 7
    other.close()  # what Neon's scale-to-zero does to an idle connection
    run.finish("partial")
    status, fetched = conn.execute("select status, rows_fetched from ingestion_runs where id = %s", (run.id,)).fetchone()
    assert (status, fetched) == ("partial", 7)
