import numpy as np
import pytest

from airatlas_api.insights import festival_kind, heating_season, spearman, tn_land_use_of


class TestSpearman:
    def test_monotonic_relations(self):
        x = list(range(20))
        assert spearman(x, [v ** 3 for v in x]) == pytest.approx(1.0)       # monotonic, not linear
        assert spearman(x, [-v for v in x]) == pytest.approx(-1.0)

    def test_ties_get_average_ranks(self):
        x = [1, 2, 2, 3, 4, 5, 6, 7, 8, 9]
        y = [1, 2, 3, 3, 5, 6, 7, 8, 9, 10]
        # Pearson of the hand-ranked vectors [1, 2.5, 2.5, 4..10] and [1, 2, 3.5, 3.5, 5..10]
        assert spearman(x, y) == pytest.approx(0.9908536585365854, abs=1e-9)

    def test_too_few_or_constant(self):
        assert spearman([1, 2, 3], [3, 2, 1]) is None
        assert spearman(list(range(12)), [5] * 12) is None

    def test_noise_is_near_zero(self):
        rng = np.random.default_rng(3)
        assert abs(spearman(rng.normal(size=500).tolist(), rng.normal(size=500).tolist())) < 0.1


def test_heating_season_months():
    assert [m for m in range(1, 13) if heating_season(m)] == [1, 2, 3, 10, 11, 12]


def test_festival_kind_from_label():
    assert festival_kind("new_years_eve_2025") == "new_years_eve"
    assert festival_kind("deepavali_2024") == "deepavali"


@pytest.mark.parametrize("name, use", [
    ("SIPCOT Industrial Park, Perundurai - TNPCB", "industrial"),
    ("SIDCO Kurichi, Coimbatore - TNPCB", "industrial"),
    ("Manali, Chennai - CPCB", "industrial"),
    ("Velachery Res. Area, Chennai - CPCB", "residential"),
    ("Perungudi, Chennai - TNPCB", None),        # no basis in the name: left unclassified, not guessed
])
def test_tamil_nadu_land_use_only_from_explicit_basis(name, use):
    got = tn_land_use_of(name)
    assert (got[0] if got else None) == use
