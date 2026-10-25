import struct
import zlib

import numpy as np
import pytest
from airatlas_aqi import Averaging, Pollutant, get_standard

from airatlas_api.heatmap import colourize
from airatlas_api.idw import Grid, _merc_y, encode_png, hex_rgb, idw

BERLIN = (52.52, 13.40)


def one(lat, lon, *pts, **kw):
    p = np.array(pts, dtype=float)
    trust = p[:, 3] if p.shape[1] > 3 else None
    return idw(np.array([lat]), np.array([lon]), p[:, 0], p[:, 1], p[:, 2], trust, **kw)[0]


class TestGrid:
    def test_rows_are_evenly_spaced_in_web_mercator_not_latitude(self):
        g = Grid(5.8, 47.2, 15.1, 55.1, width=10, height=40)
        y = _merc_y(g.lats())
        assert np.allclose(np.diff(y), np.diff(y)[0])            # even in Mercator
        assert not np.allclose(np.diff(g.lats()), np.diff(g.lats())[0])  # hence uneven in latitude
        assert g.lats()[0] < 55.1 and g.lats()[-1] > 47.2 and g.lats()[0] > g.lats()[-1]  # north first

    def test_cell_count_follows_cell_size(self):
        g = Grid.for_bbox(5.8, 47.2, 15.1, 55.1, cell_km=5)
        assert 120 < g.width < 140 and 170 < g.height < 180       # ~630 km x ~875 km
        lat, lon = g.centres()
        assert lat.size == lon.size == g.width * g.height


class TestIdw:
    def test_exact_at_a_station(self):
        assert one(*BERLIN, (*BERLIN, 42.0), (52.0, 13.0, 10.0)) == pytest.approx(42.0)

    def test_halfway_between_equal_points_is_the_mean(self):
        assert one(52.5, 13.5, (52.5, 13.0, 10.0), (52.5, 14.0, 30.0)) == pytest.approx(20.0, abs=0.01)

    def test_trusted_points_pull_harder(self):
        # same distance; the monitor (trust 1) outweighs the model point (trust 0.25)
        v = one(52.5, 13.5, (52.5, 13.0, 10.0, 1.0), (52.5, 14.0, 30.0, 0.25))
        assert v == pytest.approx((10 * 1 + 30 * 0.25) / 1.25, abs=0.01)

    def test_no_extrapolation_beyond_radius(self):
        assert np.isnan(one(54.0, 13.4, (*BERLIN, 20.0), radius_km=60))  # ~165 km away

    def test_k_nearest_limits_influence(self):
        near, far = (52.52, 13.41, 10.0), (52.52, 13.80, 500.0)
        assert one(52.52, 13.40, near, far, k=1, snap_km=0.01) == pytest.approx(10.0)

    def test_no_points_gives_no_values(self):
        out = idw(np.array([1.0, 2.0]), np.array([1.0, 2.0]), np.array([]), np.array([]), np.array([]))
        assert np.isnan(out).all()

    def test_values_stay_within_the_observed_range(self):
        rng = np.random.default_rng(1)
        pl, pn, pv = rng.uniform(50, 54, 40), rng.uniform(8, 14, 40), rng.uniform(3, 60, 40)
        g = Grid.for_bbox(8, 50, 14, 54, 20)
        lat, lon = g.centres()
        v = idw(lat, lon, pl, pn, pv, radius_km=500)
        assert np.nanmin(v) >= pv.min() - 1e-9 and np.nanmax(v) <= pv.max() + 1e-9  # IDW is a convex combination


def decode(png: bytes) -> np.ndarray:
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    i, idat, w, h = 8, b"", 0, 0
    while i < len(png):
        n, tag = struct.unpack(">I4s", png[i:i + 8])
        body, crc = png[i + 8:i + 8 + n], struct.unpack(">I", png[i + 8 + n:i + 12 + n])[0]
        assert zlib.crc32(tag + body) & 0xFFFFFFFF == crc
        if tag == b"IHDR":
            w, h = struct.unpack(">II", body[:8])
        elif tag == b"IDAT":
            idat += body
        i += 12 + n
    return np.frombuffer(zlib.decompress(idat), np.uint8).reshape(h, w * 4 + 1)[:, 1:].reshape(h, w, 4)


def test_png_round_trip():
    img = np.zeros((3, 5, 4), np.uint8)
    img[1, 2] = (255, 0, 0, 150)
    out = decode(encode_png(img))
    assert out.shape == (3, 5, 4) and (out == img).all()


def test_cells_are_coloured_by_the_engine_and_gaps_stay_transparent():
    uba = get_standard("de_uba_lqi")
    key = (Pollutant.PM25, Averaging.H1)
    rgba = colourize(uba, key, np.array([4.0, 12.0, np.nan, 60.0]))
    cats = uba.categories
    assert tuple(rgba[0, :3]) == hex_rgb(cats[0].color)   # 4 -> very good (0-5)
    assert tuple(rgba[1, :3]) == hex_rgb(cats[1].color)   # 12 -> good (6-15)
    assert rgba[2, 3] == 0                                # no data -> transparent
    assert tuple(rgba[3, :3]) == hex_rgb(cats[4].color)   # 60 -> very poor (> 50)


def test_same_concentration_differs_by_standard():
    """24-h PM2.5 of 40: 'Satisfactory' on CPCB, 'Interim target 2' against WHO."""
    v = np.array([40.0])
    cpcb = colourize(get_standard("in_cpcb_naqi"), (Pollutant.PM25, Averaging.H24), v)
    who = colourize(get_standard("who_2021_pm25"), (Pollutant.PM25, Averaging.H24), v)
    assert tuple(cpcb[0, :3]) == hex_rgb(get_standard("in_cpcb_naqi").categories[1].color)
    assert tuple(who[0, :3]) == hex_rgb(get_standard("who_2021_pm25").categories[3].color)
