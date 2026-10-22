"""Adapter parsers against responses recorded from the real APIs on 2026-10-21/22."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from conftest import load

from airatlas_ingest.adapters import cpcb, eea, firms, openaq, openmeteo, uba
from airatlas_ingest.models import StationKey

UTC = timezone.utc


class TestUba:
    def test_meta_yields_active_stations_with_codes(self):
        stations = uba.parse_meta(load("uba_meta.json"))
        s = next(s for s in stations if s.external_id == "DEBB021")
        assert (s.name, s.city, s.setting, s.station_type) == ("Potsdam-Zentrum", "Potsdam", "urban", "background")
        assert (s.lat, s.lon) == (52.4014, 13.0602) and s.meta["uba_id"] == "21"

    def test_labels_are_fixed_cet_all_year(self):
        # Summer: a "CEST" reading would be UTC+2; UBA is UTC+1 regardless.
        assert uba.parse_label("2026-07-01 12:00:00") == datetime(2026, 7, 1, 11, tzinfo=UTC)
        # Spring-forward day: 02:00 does not exist in German local time but UBA returns it.
        assert uba.parse_label("2026-03-29 02:00:00") == datetime(2026, 3, 29, 1, tzinfo=UTC)

    def test_measures(self, rejected):
        meta = load("uba_meta.json")
        id_to_code = {v[0]: v[1] for v in meta["stations"].values()}
        rows = uba.parse_measures(load("uba_measures_pm25.json"), id_to_code, rejected)
        r = next(r for r in rows if r.station.external_id == "DEBB021")
        assert r.ts == datetime(2026, 10, 19, 23, tzinfo=UTC)  # label 2026-10-20 00:00 CET
        assert set(r.values) == {"pm25"}

    def test_window_uses_hour_end_numbers(self):
        w = uba._window(datetime(2026, 10, 20, 23, tzinfo=UTC), datetime(2026, 10, 21, 5, tzinfo=UTC))
        assert w == {"date_from": "2026-10-21", "time_from": "1", "date_to": "2026-10-21", "time_to": "7"}


class TestCpcb:
    def test_parses_official_sub_indices(self, rejected):
        stations, rows = cpcb.parse_records(load("cpcb_kerala.json")["records"], rejected)
        assert {s.external_id for s in stations} == {
            "Thavakkara, Kannur - Kerala PCB", "Corporation Ground, Thrissur - Kerala PCB", "Udyogamandal, Eloor - Kerala PCB"}
        pm = next(r for r in rows if r.pollutant == "pm25")
        assert (pm.sub_min, pm.sub_avg, pm.sub_max) == (45, 49, 53)
        assert pm.reported_at == datetime(2026, 10, 21, 16, 30, tzinfo=UTC)  # 22:00 IST

    def test_duplicates_na_and_unknown_pollutants_are_counted(self, rejected):
        _, rows = cpcb.parse_records(load("cpcb_kerala.json")["records"], rejected)
        assert len(rows) == 3  # PM2.5, CO, NH3
        assert rejected["cpcb: duplicate row"] == 1
        assert rejected["cpcb: NA"] == 1
        assert rejected["cpcb: unknown pollutant Pb"] == 1


class TestOpenAQ:
    def test_locations_filter_inactive_and_map_sensors(self, rejected):
        res = load("openaq_locations_chennai.json")["results"]
        since = datetime(2026, 9, 1, tzinfo=UTC)
        stations = openaq.parse_locations(res, frozenset(), since, rejected)
        names = {s.name for s in stations}
        assert "Alandur Bus Depot" not in names  # last data 2018
        v = next(s for s in stations if s.name.startswith("Velachery"))
        assert v.kind == "reference" and {p for p, _u in v.meta["sensors"].values()} >= {"pm25", "no2"}

    def test_excluded_providers(self, rejected):
        res = load("openaq_locations_chennai.json")["results"]
        assert openaq.parse_locations(res, frozenset({"CPCB"}), datetime(2026, 9, 1, tzinfo=UTC), rejected) == []

    def test_mislabelled_co_ppb_is_treated_as_mg(self, rejected):
        h = load("openaq_hours_co.json")["results"]
        rows = openaq.parse_hours(h, StationKey(source="openaq", external_id="2586"), "co", "ppb", rejected)
        assert [r.values["co"] for r in rows] == [0.22, 0.318, 0.5]
        assert rows[0].ts == datetime(2026, 10, 16, 23, 30, tzinfo=UTC)
        assert rejected["openaq: CO 'ppb' relabelled mg/m3 (corrected, kept)"] == 3

    @pytest.mark.parametrize("value, units, expected", [(5300, "µg/m³", 5.3), (1, "ppm", 1.1449), (500, "ppb", 0.5725)])
    def test_co_to_mg(self, rejected, value, units, expected):
        assert openaq.to_canonical("co", value, units, rejected) == pytest.approx(expected, rel=1e-3)

    def test_low_coverage_hours_dropped(self, rejected):
        row = load("openaq_hours_co.json")["results"][0] | {"coverage": {"percentCoverage": 50.0}}
        assert openaq.parse_hours([row], StationKey(source="openaq", external_id="1"), "co", "mg/m3", rejected) == []
        assert rejected["openaq: hour below 75% coverage"] == 1


class TestOpenMeteo:
    def test_multi_location_aq(self, rejected):
        keys = [StationKey(source="open_meteo", external_id=x) for x in ("chennai", "dubai")]
        rows = openmeteo.parse_aq(load("openmeteo_aq_multi.json"), keys, datetime(2100, 1, 1, tzinfo=UTC), rejected)
        dubai = [r for r in rows if r.station.external_id == "dubai"]
        assert dubai and "dust" in dubai[0].values
        assert all(r.values["co"] < 10 for r in rows)  # converted ug/m3 -> mg/m3

    def test_forecast_hours_are_not_stored(self, rejected):
        keys = [StationKey(source="open_meteo", external_id=x) for x in ("a", "b")]
        payload = load("openmeteo_aq_multi.json")
        first = datetime.fromisoformat(payload[0]["hourly"]["time"][0]).replace(tzinfo=UTC)
        rows = openmeteo.parse_aq(payload, keys, first, rejected)
        assert {r.ts for r in rows} == {first}

    def test_weather(self, rejected):
        keys = [StationKey(source="open_meteo", external_id=x) for x in ("a", "b")]
        rows = openmeteo.parse_weather(load("openmeteo_weather_multi.json"), keys, datetime(2100, 1, 1, tzinfo=UTC), rejected)
        assert rows and all(r.rh_pct is not None and 0 <= r.wind_dir_deg <= 360 for r in rows)

    def test_location_count_mismatch_fails_loudly(self, rejected):
        with pytest.raises(ValueError):
            openmeteo.parse_aq(load("openmeteo_aq_multi.json"), [StationKey(source="open_meteo", external_id="x")],
                               datetime(2100, 1, 1, tzinfo=UTC), rejected)


class TestFirms:
    def test_csv(self, rejected):
        rows = firms.parse_csv(load("firms_uae.csv"), 3, rejected)
        assert rows and rows[0].detected_at == datetime(2026, 10, 15, 9, 9, tzinfo=UTC)  # acq_time 909 = 09:09 UTC
        assert rows[0].daynight == "D" and rows[0].region_id == 3

    def test_error_text_raises(self, rejected):
        with pytest.raises(Exception, match="unexpected"):
            firms.parse_csv("Invalid MAP_KEY.", 3, rejected)


class TestEea:
    def test_table_rows_map_to_uba_station_codes_in_utc(self, rejected):
        base = {"Samplingpoint": "DE/SPO.DE_DEBB021_PM2_dataGroup1", "Pollutant": 6001, "Unit": "ug.m-3", "AggType": "hour"}
        rows = eea.parse_table([
            base | {"Start": datetime(2026, 10, 20, 0), "Value": Decimal("6.0"), "Validity": 1},
            base | {"Start": datetime(2026, 10, 22, 23), "Value": Decimal("-999"), "Validity": -1},
        ], rejected)
        assert len(rows) == 1 and rows[0].station == StationKey(source="uba", external_id="DEBB021")
        assert rows[0].ts == datetime(2026, 10, 19, 23, tzinfo=UTC)
        assert rejected["eea: invalid or placeholder"] == 1


def test_event_windows_are_local_days():
    from airatlas_ingest.events import EVENTS

    nye = next(e for e in EVENTS if e.label == "new_years_eve_2025")
    start, end = nye.window("uae")
    assert start.utcoffset() == timedelta(hours=4) and (end - start).days == 7
    assert start.date() == date(2025, 12, 28)
