from datetime import datetime, timedelta, timezone

import pytest
from airatlas_aqi import get_standard

from airatlas_api import caching
from airatlas_api.evaluate import evaluate_station, freshness, summarize_area

UTC = timezone.utc
NOW = datetime(2026, 10, 22, 12, 40, tzinfo=UTC)


class TestCaching:
    @pytest.mark.parametrize("now, ttl", [
        (datetime(2026, 1, 1, 10, 0, tzinfo=UTC), 25 * 60),      # before :25 -> this hour's :25
        (datetime(2026, 1, 1, 10, 25, tzinfo=UTC), 60 * 60),     # exactly :25 -> next hour
        (datetime(2026, 1, 1, 10, 40, tzinfo=UTC), 45 * 60),
    ])
    def test_live_ttl_ends_when_next_ingestion_lands(self, now, ttl):
        assert caching.seconds_until_next_ingest(now) == ttl

    def test_live_header_never_below_a_minute(self):
        h = caching.header(caching.Policy.LIVE, datetime(2026, 1, 1, 10, 24, 50, tzinfo=UTC))
        assert "s-maxage=60," in h and "stale-while-revalidate" in h

    def test_no_store_for_health(self):
        assert caching.header(caching.Policy.NONE) == "no-store"


class TestFreshness:
    @pytest.mark.parametrize("age_h, kind, expected", [
        (1, "reference", "fresh"), (4, "reference", "fresh"), (6, "reference", "stale"),
        (6, "modeled", "fresh"), (8, "modeled", "stale"), (25, "reference", "unavailable"),
    ])
    def test_thresholds(self, age_h, kind, expected):
        assert freshness(NOW - timedelta(hours=age_h), kind, NOW) == expected

    def test_no_data_is_unavailable(self):
        assert freshness(None, "reference", NOW) == "unavailable"


def rows(hours, **values):
    end = NOW.replace(minute=0)
    return [{"ts": end - timedelta(hours=h), **values} for h in range(hours)]


class TestEvaluateStation:
    def test_uba_from_one_hour(self):
        out = evaluate_station(get_standard("de_uba_lqi"), rows(1, pm25=12.0, no2=40.0), "reference", NOW)
        assert out["freshness"] == "fresh" and out["aqi"]["category"]["key"] == "moderate"  # NO2 40 -> class 3
        assert out["concentrations"] == {"pm25": 12.0, "no2": 40.0}

    def test_cpcb_needs_a_full_day(self):
        std = get_standard("in_cpcb_naqi")
        short = evaluate_station(std, rows(7, pm25=40.0, pm10=80.0, no2=20.0), "modeled", NOW)
        assert short["aqi"]["status"] == "insufficient_data" and short["aqi"]["value"] is None
        full = evaluate_station(std, rows(24, pm25=40.0, pm10=80.0, no2=20.0), "modeled", NOW)
        assert full["aqi"]["value"] == 80  # PM10 80 -> 80; PM2.5 40 -> 66.7

    def test_unavailable_station_gets_no_numbers(self):
        old = [{"ts": NOW - timedelta(hours=30), "pm25": 500.0}]
        out = evaluate_station(get_standard("eu_eaqi"), old, "reference", NOW)
        assert out["aqi"] is None and out["concentrations"] is None and out["freshness"] == "unavailable"

    def test_list_mode_drops_detail(self):
        out = evaluate_station(get_standard("eu_eaqi"), rows(1, pm25=3.0), "reference", NOW, detail=False)
        assert "sub_indices" not in out["aqi"]


class TestAreaSummary:
    def e(self, kind, value, fresh="fresh"):
        return {"kind": kind, "freshness": fresh, "aqi": {"value": value} if value is not None else None}

    def test_median_of_measured_ignores_models(self):
        s = summarize_area([self.e("reference", 50), self.e("reference", 180), self.e("reference", 90), self.e("modeled", 10)])
        assert s == {"value": 90, "basis": "measured", "n_stations": 3}

    def test_falls_back_to_model_and_says_so(self):
        s = summarize_area([self.e("reference", None), self.e("modeled", 3)])
        assert s["basis"] == "modeled" and s["value"] == 3

    def test_nothing_usable_is_none(self):
        assert summarize_area([self.e("reference", 40, fresh="unavailable")]) is None
