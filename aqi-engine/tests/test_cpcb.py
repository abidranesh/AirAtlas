import pytest

from airatlas_aqi import Averaging, Pollutant, Status, get_standard

P, A = Pollutant, Averaging
cpcb = get_standard("in_cpcb_naqi")


def subs(result):
    return {s.pollutant: s.value for s in result.sub_indices}


def test_official_calculator_example():
    """Inputs and outputs shown on Sheet1 of CPCB's AQI-Calculator.xls."""
    r = cpcb.compute({
        (P.PM10, A.H24): 121, (P.PM25, A.H24): 34, (P.NO2, A.H24): 8,
        (P.O3, A.H8_MAX24): 57, (P.NH3, A.H24): 34,
    })
    s = subs(r)
    assert s[P.PM10] == pytest.approx(114.0)
    assert s[P.PM25] == pytest.approx(56.6667, abs=1e-3)
    assert s[P.NO2] == pytest.approx(10.0)
    assert s[P.O3] == pytest.approx(57.0)
    assert s[P.NH3] == pytest.approx(8.5)
    assert (r.value, r.category.key, r.dominant, r.status) == (114, "moderate", (P.PM10,), Status.OK)


def test_about_aqi_examples_and_documented_discrepancy():
    # "75 at 45 ug/m3" and "100 at 60 ug/m3" agree with the calculator...
    for c, expected in [(45, 75), (60, 100)]:
        assert subs(cpcb.compute({(P.PM25, A.H24): c, (P.PM10, A.H24): 0, (P.NO2, A.H24): 0}))[P.PM25] == expected
    # ...but "51 at 31" uses the EPA form; the calculator (which we follow) gives 51.67.
    s = subs(cpcb.compute({(P.PM25, A.H24): 31, (P.PM10, A.H24): 0, (P.NO2, A.H24): 0}))
    assert s[P.PM25] == pytest.approx(51.667, abs=1e-3)


@pytest.mark.parametrize("pollutant", list(cpcb.spec["pollutants"]))
def test_every_breakpoint_maps_to_its_index_point(pollutant):
    cfg = cpcb.spec["pollutants"][pollutant]
    key = (P(pollutant), A(cfg["averaging"]))
    for bp, idx in zip(cfg["breakpoints"], cpcb.spec["index_points"]):
        assert cpcb.sub_indices({key: bp})[0].value == pytest.approx(idx)


@pytest.mark.parametrize(
    "pollutant, avg, c, expected",
    [
        (P.PM10, A.H24, 510, 500),        # 400 + 80 * 100/80
        (P.PM25, A.H24, 380, 500),        # 400 + 130 * 100/130
        (P.NO2, A.H24, 520, 500),
        (P.CO, A.H8_MAX24, 51, 500),
        (P.SO2, A.H24, 2400, 500),
    ],
)
def test_severe_band_extends_last_slope(pollutant, avg, c, expected):
    assert cpcb.sub_indices({(pollutant, avg): c})[0].value == pytest.approx(expected)


def test_beyond_500_is_flagged_not_capped():
    s = cpcb.sub_indices({(P.PM25, A.H24): 500})[0]
    assert s.value == pytest.approx(400 + 250 * 100 / 130)
    assert s.beyond_scale and s.category.key == "severe"


def test_o3_has_no_jump_at_748():
    """The calculator's > 748 branch uses (C - 400); we use (C - 748) so the curve is continuous."""
    below = cpcb.sub_indices({(P.O3, A.H8_MAX24): 747.999})[0].value
    above = cpcb.sub_indices({(P.O3, A.H8_MAX24): 748.001})[0].value
    assert above - below < 0.01


@pytest.mark.parametrize(
    "conc, reason",
    [
        ({(P.PM25, A.H24): 80, (P.NO2, A.H24): 30}, "at least 3"),
        ({(P.NO2, A.H24): 30, (P.SO2, A.H24): 10, (P.O3, A.H8_MAX24): 50}, "pm10, pm25"),
    ],
)
def test_minimum_data_rule(conc, reason):
    r = cpcb.compute(conc)
    assert r.status is Status.INSUFFICIENT and r.value is None
    assert reason in r.notes[0]


def test_category_edges_on_rounded_value():
    def aqi(pm25):
        return cpcb.compute({(P.PM25, A.H24): pm25, (P.PM10, A.H24): 0, (P.NO2, A.H24): 0})

    assert (aqi(30).value, aqi(30).category.key) == (50, "good")
    assert (aqi(30.2).value, aqi(30.2).category.key) == (50, "good")  # 50.33 rounds to 50
    assert (aqi(30.4).value, aqi(30.4).category.key) == (51, "satisfactory")  # 50.67


def test_ties_report_all_dominant_pollutants():
    r = cpcb.compute({(P.PM10, A.H24): 100, (P.PM25, A.H24): 60, (P.NO2, A.H24): 10})
    assert r.value == 100 and set(r.dominant) == {P.PM10, P.PM25}
