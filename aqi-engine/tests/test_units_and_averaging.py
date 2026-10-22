from datetime import datetime, timedelta, timezone

import pytest

from airatlas_aqi import Pollutant, convert, normalize_unit
from airatlas_aqi.averaging import max_rolling_mean, rolling_mean
from airatlas_aqi.base import round_half_up, truncate
from airatlas_aqi.units import molar_volume_l

P = Pollutant


class TestUnits:
    def test_molar_volume_reference_conditions(self):
        assert molar_volume_l(25) == pytest.approx(24.465, abs=1e-3)
        assert molar_volume_l(20) == pytest.approx(24.055, abs=1e-3)

    @pytest.mark.parametrize(
        "pollutant, ppb, temp_c, ug",
        [
            (P.NO2, 1, 25, 1.8805),   # US-EPA / UAE convention
            (P.NO2, 1, 20, 1.9125),   # EU directive convention for gases (2008/50/EC uses 1.91)
            (P.O3, 1, 20, 1.9953),    # EU uses ~2.00
            (P.SO2, 1, 25, 2.6186),
            (P.NH3, 1, 25, 0.6961),
        ],
    )
    def test_ppb_to_ugm3(self, pollutant, ppb, temp_c, ug):
        assert convert(ppb, pollutant, "ppb", "ug/m3", temp_c=temp_c) == pytest.approx(ug, rel=1e-3)

    def test_co_ppm_goes_to_canonical_mg(self):
        assert convert(1, P.CO, "ppm") == pytest.approx(1.1449, rel=1e-3)

    def test_round_trip(self):
        x = convert(convert(37.2, P.O3, "ug/m3", "ppb"), P.O3, "ppb", "ug/m3")
        assert x == pytest.approx(37.2)

    def test_mass_units_scale(self):
        assert convert(1.2, P.CO, "mg/m3", "ug/m3") == pytest.approx(1200)
        assert convert(500, P.PB, "ng/m3", "ug/m3") == pytest.approx(0.5)

    def test_unicode_aliases(self):
        for u in ("µg/m³", "μg/m³", "µg/m3", "UG/M3"):
            assert normalize_unit(u) == "ug/m3"

    def test_particulates_have_no_volume_unit(self):
        with pytest.raises(ValueError, match="not a gas"):
            convert(10, P.PM25, "ppb")

    def test_unknown_unit(self):
        with pytest.raises(ValueError):
            normalize_unit("furlongs")


class TestNumeric:
    @pytest.mark.parametrize("x, d, out", [(60.256, 1, 60.2), (2.965, 1, 2.9), (135.485, 0, 135), (38.4567, 1, 38.4)])
    def test_truncate_matches_uae_guideline_examples(self, x, d, out):
        assert truncate(x, d) == out

    @pytest.mark.parametrize("x, out", [(50.4, 50), (50.5, 51), (50.6, 51), (115.913, 116)])
    def test_round_half_up(self, x, out):
        assert round_half_up(x) == out


T0 = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)


def series(values):
    """values[0] is the hour starting at T0, values[1] the hour before, ..."""
    return {T0 - timedelta(hours=k): v for k, v in enumerate(values)}


class TestAveraging:
    def test_rolling_mean_ignores_missing(self):
        s = series([10, None, 20, 30])
        assert rolling_mean(s, T0, 4, min_valid=3) == pytest.approx(20)

    def test_rolling_mean_requires_completeness(self):
        s = series([10, None, None, 30])
        assert rolling_mean(s, T0, 4, min_valid=3) is None

    def test_window_does_not_include_future_or_older_hours(self):
        s = series([1] * 8 + [1000])  # 9th hour back must be outside an 8-h window
        s[T0 + timedelta(hours=1)] = 1000  # a future hour must be ignored
        assert rolling_mean(s, T0, 8, 8) == 1

    def test_max_rolling_mean_over_24h(self):
        # 8 hours of 100 ending 10 h ago, zeros elsewhere: the max 8-h mean is 100.
        vals = [0.0] * 24
        for k in range(10, 18):
            vals[k] = 100.0
        assert max_rolling_mean(series(vals), T0, 8, 24, 6) == pytest.approx(100)
