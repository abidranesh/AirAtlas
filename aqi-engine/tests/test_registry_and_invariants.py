"""Cross-standard invariants: every standard must satisfy these, including future ones."""

import math

import pytest

from airatlas_aqi import COMMON_SCALES, LOCAL_STANDARD, STANDARDS, Averaging, Pollutant, get_standard, standard_for
from airatlas_aqi.docgen import render_all

ALL = [get_standard(code) for code in STANDARDS]


def test_every_region_has_a_local_standard_and_common_scales_exist():
    for region in ("tamil_nadu", "kerala", "uae", "germany"):
        assert standard_for(region).code == LOCAL_STANDARD[region]
        for scale in COMMON_SCALES:
            assert standard_for(region, scale).code == scale


def test_unknown_lookups_fail_loudly():
    with pytest.raises(KeyError):
        get_standard("xx_made_up")
    with pytest.raises(ValueError):
        standard_for("germany", "de_uba_lqi")  # not a common scale


@pytest.mark.parametrize("std", ALL, ids=lambda s: s.code)
def test_every_table_documents_its_sources(std):
    assert std.spec["sources"] and all(s["url"].startswith("https://") for s in std.spec["sources"])
    assert std.spec["rules"]


@pytest.mark.parametrize("std", ALL, ids=lambda s: s.code)
def test_sub_index_never_decreases_as_concentration_rises(std):
    for p, avg in std.inputs():
        prev = -math.inf
        for i in range(0, 4000):
            c = i * 0.25 if p is not Pollutant.CO else i * 0.02
            subs = [s for s in std.sub_indices({(p, avg): c}) if s.averaging is avg]
            if not subs:
                continue  # e.g. UAE 1-h O3 below 200 is not used
            assert subs[0].value >= prev, (std.code, p, avg, c)
            prev = subs[0].value


@pytest.mark.parametrize("std", ALL, ids=lambda s: s.code)
def test_categories_are_contiguous(std):
    cats = std.categories
    assert [c.level for c in cats] == list(range(1, len(cats) + 1))
    if std.is_index_scale:
        for a, b in zip(cats, cats[1:]):
            assert b.index_range[0] == a.index_range[1] + 1


@pytest.mark.parametrize("std", ALL, ids=lambda s: s.code)
def test_invalid_concentrations_are_rejected(std):
    p, avg = std.inputs()[0]
    for bad in (-1.0, math.nan, math.inf):
        with pytest.raises(ValueError):
            std.compute({(p, avg): bad})


@pytest.mark.parametrize("std", ALL, ids=lambda s: s.code)
def test_empty_input_is_insufficient_not_zero(std):
    r = std.compute({})
    assert r.value is None and r.status == "insufficient_data"


def test_docs_are_generated_from_tables():
    """Fails when a JSON table changed but docs were not regenerated (python -m airatlas_aqi.docgen)."""
    for path, content in render_all().items():
        assert path.exists(), f"missing {path}; run python -m airatlas_aqi.docgen"
        assert path.read_text(encoding="utf-8") == content, f"{path.name} is stale; run python -m airatlas_aqi.docgen"
