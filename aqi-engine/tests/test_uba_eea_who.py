import json
from pathlib import Path

import pytest

from airatlas_aqi import Averaging, Pollutant, Status, get_standard

P, A = Pollutant, Averaging
uba = get_standard("de_uba_lqi")
eea = get_standard("eu_eaqi")
who = get_standard("who_2021_pm25")

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "uba_live_index.json").read_text(encoding="utf-8"))


class TestUbaAgainstLiveApi:
    """UBA's API returns its own class (0 = very good .. 4 = very poor) next to each value."""

    def test_every_observed_value_classified_like_uba(self):
        mismatches = [
            (p, v, idx, lvl)
            for p, v, idx in FIXTURE["pairs"]
            if (lvl := uba.sub_indices({(P(p), A.H1): v})[0].value) != idx + 1
        ]
        assert not mismatches, mismatches[:10]

    def test_total_index_matches_for_station_hours(self):
        for h in FIXTURE["station_hours"]:
            r = uba.compute({(P(p), A.H1): v for p, v in h["values"].items()})
            assert r.value == h["uba_total_index"] + 1, h

    def test_fixture_covers_all_five_classes(self):
        assert {idx for _, _, idx in FIXTURE["pairs"]} == {0, 1, 2, 3, 4}


@pytest.mark.parametrize("standard", [uba, eea], ids=["uba", "eea"])
def test_step_band_edges(standard):
    for p, cfg in standard.spec["pollutants"].items():
        for level, upper in enumerate(cfg["upper"], start=1):
            if upper is None:
                continue
            assert standard.sub_indices({(P(p), A.H1): upper})[0].value == level
            assert standard.sub_indices({(P(p), A.H1): upper + 1})[0].value == level + 1


class TestEea:
    def test_rounding_half_up_before_banding(self):
        assert eea.sub_indices({(P.PM25, A.H1): 5.49})[0].category.key == "good"
        assert eea.sub_indices({(P.PM25, A.H1): 5.5})[0].category.key == "fair"

    def test_worst_pollutant_wins(self):
        r = eea.compute({(P.PM25, A.H1): 12, (P.NO2, A.H1): 70, (P.O3, A.H1): 30})
        assert (r.category.key, r.dominant, r.status) == ("poor", (P.NO2,), Status.OK)

    def test_without_particulates_is_partial(self):
        r = eea.compute({(P.NO2, A.H1): 20})
        assert r.status is Status.PARTIAL and r.category.key == "fair"

    def test_top_band_is_open_ended(self):
        assert eea.sub_indices({(P.PM10, A.H1): 5000})[0].category.key == "extremely_poor"


class TestWho:
    @pytest.mark.parametrize(
        "pm25, key",
        [(15, "aqg"), (15.01, "it4"), (25, "it4"), (37.5, "it3"), (37.6, "it2"), (75, "it1"), (75.1, "above_it1")],
    )
    def test_interim_targets_without_rounding(self, pm25, key):
        assert who.compute({(P.PM25, A.H24): pm25}).category.key == key

    def test_reports_guideline_multiple(self):
        assert who.compute({(P.PM25, A.H24): 45}).extra["who_multiple"] == pytest.approx(3.0)

    def test_needs_pm25(self):
        assert who.compute({(P.PM10, A.H24): 50}).status is Status.INSUFFICIENT
