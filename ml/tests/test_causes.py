from datetime import datetime, timezone

import pytest

from airatlas_ml.causes import Context, Fire, angle_diff, bearing_deg, haversine_km, hints_for, mean_wind

CHENNAI = (13.08, 80.27)
T = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)


def kinds(hints):
    return [(h.kind, h.confidence) for h in hints]


class TestGeometry:
    def test_bearings(self):
        assert bearing_deg(0, 0, 1, 0) == pytest.approx(0, abs=0.1)     # north
        assert bearing_deg(0, 0, 0, 1) == pytest.approx(90, abs=0.1)    # east
        assert bearing_deg(0, 0, -1, 0) == pytest.approx(180, abs=0.1)
        assert bearing_deg(0, 0, 0, -1) == pytest.approx(270, abs=0.1)

    def test_angle_difference_wraps_around_north(self):
        assert angle_diff(350, 10) == pytest.approx(20)
        assert angle_diff(10, 350) == pytest.approx(20)
        assert angle_diff(90, 270) == pytest.approx(180)

    def test_vector_mean_wind_across_north(self):
        direction, speed = mean_wind([(350, 4), (10, 4)])
        assert angle_diff(direction, 0) < 0.01 and speed == 4      # not 180 deg

    def test_distance(self):
        assert haversine_km(*CHENNAI, 13.08 + 1, 80.27) == pytest.approx(111.2, abs=0.5)


def fire(lat, lon, frp=10.0, persistent=False):
    return Fire(lat, lon, frp, T, persistent)


class TestFires:
    def test_fires_upwind_are_flagged_and_downwind_ones_are_not(self):
        west = [fire(13.08, 79.6 + i * 0.01) for i in range(6)]          # ~70 km west of Chennai
        upwind = Context(*CHENNAI, "pm25", wind=[(270, 3.0)] * 4, fires=west)     # wind from the west
        downwind = Context(*CHENNAI, "pm25", wind=[(90, 3.0)] * 4, fires=west)    # wind from the east
        assert ("fire_upwind", "high") in kinds(hints_for(upwind))
        assert not any(k == "fire_upwind" for k, _ in kinds(hints_for(downwind)))

    def test_persistent_hotspots_are_not_called_fires(self):
        flares = [fire(13.08, 79.6, persistent=True)]
        h = kinds(hints_for(Context(*CHENNAI, "pm25", wind=[(270, 3.0)], fires=flares)))
        assert ("industrial_heat_upwind", "low") in h and not any(k == "fire_upwind" for k, _ in h)

    def test_far_fires_are_ignored(self):
        far = [fire(13.08, 77.5)]  # ~300 km
        assert hints_for(Context(*CHENNAI, "pm25", wind=[(270, 3.0)], fires=far)) == []

    def test_without_wind_only_close_fires_count_with_low_confidence(self):
        close = [fire(13.2, 80.27)]
        assert kinds(hints_for(Context(*CHENNAI, "pm25", fires=close))) == [("fire_nearby", "low")]


def test_dust_only_for_particles():
    assert ("dust", "high") in kinds(hints_for(Context(25.2, 55.3, "pm10", dust_max=180)))
    assert ("dust", "medium") in kinds(hints_for(Context(25.2, 55.3, "pm25", dust_max=60)))
    assert hints_for(Context(25.2, 55.3, "no2", dust_max=180)) == []


def test_festival_and_stagnation():
    h = kinds(hints_for(Context(*CHENNAI, "pm25", festival="Deepavali", wind=[(0, 0.8)] * 3, precip_mm=0)))
    assert h[0] == ("festival", "high") and ("stagnation", "medium") in h


def test_rain_rules_out_stagnation():
    assert hints_for(Context(*CHENNAI, "pm25", wind=[(0, 0.8)] * 3, precip_mm=6)) == []


@pytest.mark.parametrize("co, expected", [((5, 10), ("regional", "medium")), ((1, 10), ("local", "low")), ((1, 2), None)])
def test_regional_or_local(co, expected):
    h = kinds(hints_for(Context(*CHENNAI, "pm25", co_stations=co)))
    assert (expected in h) if expected else h == []


def test_traffic_hint_only_for_no2_at_traffic_sites():
    assert ("traffic", "low") in kinds(hints_for(Context(52.5, 13.4, "no2", station_type="traffic")))
    assert hints_for(Context(52.5, 13.4, "pm25", station_type="traffic")) == []


def test_hints_are_ordered_by_confidence():
    ctx = Context(*CHENNAI, "pm25", festival="Deepavali", co_stations=(1, 10), wind=[(0, 0.5)], precip_mm=0)
    assert [h.confidence for h in hints_for(ctx)] == ["high", "medium", "low"]


def test_fire_confidence_scales_with_evidence():
    def conf(n, frp=2.0):
        fires = [fire(13.08, 79.6 + i * 0.01, frp=frp) for i in range(n)]
        return dict(kinds(hints_for(Context(*CHENNAI, "pm25", wind=[(270, 3.0)], fires=fires)))).get("fire_upwind")
    assert (conf(1), conf(3), conf(10), conf(2, frp=30)) == ("low", "medium", "high", "high")


def test_isolated_single_hour_spike_is_flagged_as_possible_artefact():
    h = kinds(hints_for(Context(*CHENNAI, "pm10", hours=1, ratio=13.4, co_stations=(1, 16))))
    assert ("possible_artefact", "low") in h
    assert "possible_artefact" not in dict(kinds(hints_for(Context(*CHENNAI, "pm10", hours=4, ratio=13.4))))
