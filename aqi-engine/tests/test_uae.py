from datetime import datetime, timedelta, timezone

import pytest

from airatlas_aqi import Averaging, Pollutant, Status, get_standard

P, A = Pollutant, Averaging
uae = get_standard("ae_eaqi")


def sub(pollutant, avg, c):
    s = uae.sub_indices({(pollutant, avg): c})
    return s[0] if s else None


# Worked examples from section IV of the NCM 2023 guideline.
@pytest.mark.parametrize(
    "pollutant, avg, c, expected",
    [
        (P.O3, A.H8, 135.4850, 116),
        (P.CO, A.H8, 2.965, 27),
        (P.SO2, A.H1, 100.678, 52),
        (P.NO2, A.H1, 98.896, 49),
        (P.PM10, A.H24, 63.521, 42),
        (P.PM25, A.H24, 60.256, 99),
    ],
)
def test_guideline_worked_examples(pollutant, avg, c, expected):
    assert sub(pollutant, avg, c).value == expected


def test_guideline_overall_example():
    r = uae.compute({
        (P.O3, A.H8): 135.4850, (P.CO, A.H8): 2.965, (P.SO2, A.H1): 100.678,
        (P.NO2, A.H1): 98.896, (P.PM10, A.H24): 63.521, (P.PM25, A.H24): 60.256,
    })
    assert (r.value, r.category.key, r.dominant, r.status) == (116, "usg", (P.O3,), Status.OK)


@pytest.mark.parametrize("pollutant", ["co", "no2", "pm10", "pm25"])
def test_segment_endpoints(pollutant):
    cfg = uae.spec["pollutants"][pollutant]
    (avg, acfg), = cfg["averagings"].items()
    for bp_lo, bp_hi, i_lo, i_hi in acfg["segments"]:
        assert sub(P(pollutant), A(avg), bp_lo).value == i_lo
        assert sub(P(pollutant), A(avg), bp_hi).value == i_hi


def test_truncation_closes_gaps_between_bands():
    # 100.9 truncates to 100 (Good), never falls into the 100-101 gap.
    assert sub(P.NO2, A.H1, 100.9).value == 50
    assert sub(P.PM25, A.H24, 50.49).value == 50


class TestOzoneSelection:
    def test_low_1h_is_ignored(self):
        s = uae.sub_indices({(P.O3, A.H1): 150, (P.O3, A.H8): 110})
        assert [(x.averaging, x.value) for x in s] == [(A.H8, 74)]  # 49/19 * 9 + 51 = 74.2

    def test_takes_max_of_1h_and_8h(self):
        s = uae.sub_indices({(P.O3, A.H1): 350, (P.O3, A.H8): 110})[0]
        assert (s.averaging, s.value) == (A.H1, 168)

    def test_8h_above_392_switches_to_1h(self):
        s = uae.sub_indices({(P.O3, A.H1): 900, (P.O3, A.H8): 400})[0]
        assert s.averaging is A.H1 and s.category.key == "hazardous"


class TestSO2Selection:
    def test_1h_used_up_to_797(self):
        assert uae.sub_indices({(P.SO2, A.H1): 797, (P.SO2, A.H24): 900})[0].averaging is A.H1

    def test_24h_used_above_797(self):
        s = uae.sub_indices({(P.SO2, A.H1): 900, (P.SO2, A.H24): 1000})[0]
        assert (s.averaging, s.category.key) == (A.H24, "very_unhealthy")

    def test_epa_fallback_when_24h_too_low(self):
        assert uae.sub_indices({(P.SO2, A.H1): 900, (P.SO2, A.H24): 300})[0].value == 200


def test_above_top_breakpoint_is_extrapolated_and_flagged():
    s = sub(P.PM10, A.H24, 700)
    assert s.beyond_scale and s.value > 500 and s.category.key == "hazardous"


T0 = datetime(2026, 7, 1, 12, tzinfo=timezone.utc)


def hourly(values):
    return {T0 - timedelta(hours=k): v for k, v in enumerate(values)}


class TestValidationRules:
    def test_complete_24h_mean(self):
        inputs = uae.from_hourly({P.PM10: hourly([100.0] * 24)}, T0)
        assert inputs[(P.PM10, A.H24)] == pytest.approx(100)

    def test_incomplete_and_below_standard_is_null(self):
        inputs = uae.from_hourly({P.PM10: hourly([100.0] * 10)}, T0)
        assert (P.PM10, A.H24) not in inputs

    def test_incomplete_but_above_standard_uses_max_hourly(self):
        inputs = uae.from_hourly({P.PM10: hourly([100.0] * 9 + [400.0])}, T0)
        assert inputs[(P.PM10, A.H24)] == 400

    def test_hourly_values_above_table4_are_invalid(self):
        inputs = uae.from_hourly({P.PM10: hourly([3000.0] + [50.0] * 23)}, T0)
        assert inputs[(P.PM10, A.H24)] == pytest.approx(50)  # 23 valid hours, 3000 dropped

    def test_evaluate_end_to_end(self):
        r = uae.evaluate({P.PM25: hourly([55.0] * 24), P.NO2: hourly([80.0])}, T0)
        assert (r.value, r.dominant) == (73, (P.PM25,))
