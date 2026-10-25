"""Inverse Distance Weighting on a Web-Mercator-aligned grid, plus a tiny PNG encoder.

Pure numpy; no GIS dependencies. Used to draw the interpolated heatmap overlay.

    v(x) = sum_i q_i * v_i / d_i^p  /  sum_i q_i / d_i^p     over the k nearest points within R

q_i is a per-point trust weight (monitor > low-cost sensor > model point), p the power (2),
k bounds the neighbourhood so distant stations do not flatten local structure, and cells
farther than R from every point are left empty (NaN) instead of extrapolated.
"""

from __future__ import annotations

import math
import struct
import zlib
from dataclasses import dataclass

import numpy as np

KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LON_EQUATOR = 111.320


def _merc_y(lat_deg: np.ndarray | float) -> np.ndarray:
    lat = np.radians(lat_deg)
    return np.log(np.tan(np.pi / 4 + lat / 2))


def _inv_merc_y(y: np.ndarray) -> np.ndarray:
    return np.degrees(2 * np.arctan(np.exp(y)) - np.pi / 2)


@dataclass(frozen=True)
class Grid:
    """Cell centres for an image covering bbox. Rows go north -> south (image order) and are spaced
    evenly in Web Mercator y, so Leaflet can stretch the PNG over the bbox without distortion."""

    west: float
    south: float
    east: float
    north: float
    width: int
    height: int

    @classmethod
    def for_bbox(cls, west: float, south: float, east: float, north: float, cell_km: float) -> Grid:
        mid_lat = (south + north) / 2
        width = max(2, round((east - west) * KM_PER_DEG_LON_EQUATOR * math.cos(math.radians(mid_lat)) / cell_km))
        height = max(2, round((north - south) * KM_PER_DEG_LAT / cell_km))
        return cls(west, south, east, north, width, height)

    def lons(self) -> np.ndarray:
        step = (self.east - self.west) / self.width
        return self.west + step * (np.arange(self.width) + 0.5)

    def lats(self) -> np.ndarray:
        y_top, y_bottom = _merc_y(self.north), _merc_y(self.south)
        y = y_top - (y_top - y_bottom) * (np.arange(self.height) + 0.5) / self.height
        return _inv_merc_y(y)

    def centres(self) -> tuple[np.ndarray, np.ndarray]:
        """Flattened (lat, lon) of every cell, row-major from the top-left."""
        lat, lon = np.meshgrid(self.lats(), self.lons(), indexing="ij")
        return lat.ravel(), lon.ravel()


def idw(
    cell_lat: np.ndarray,
    cell_lon: np.ndarray,
    pt_lat: np.ndarray,
    pt_lon: np.ndarray,
    values: np.ndarray,
    trust: np.ndarray | None = None,
    *,
    power: float = 2.0,
    k: int = 8,
    radius_km: float = 60.0,
    snap_km: float = 0.5,
    chunk: int = 4096,
) -> np.ndarray:
    """IDW estimate for every cell; NaN where no point lies within radius_km."""
    n_cells, n_pts = cell_lat.size, pt_lat.size
    out = np.full(n_cells, np.nan)
    if n_pts == 0:
        return out
    trust = np.ones(n_pts) if trust is None else np.asarray(trust, dtype=float)
    k = min(k, n_pts)
    kx = KM_PER_DEG_LON_EQUATOR * np.cos(np.radians(pt_lat))  # local equirectangular scale, fine at < 100 km
    for start in range(0, n_cells, chunk):
        sl = slice(start, start + chunk)
        dx = (cell_lon[sl, None] - pt_lon[None, :]) * kx[None, :]
        dy = (cell_lat[sl, None] - pt_lat[None, :]) * KM_PER_DEG_LAT
        d = np.hypot(dx, dy)                                     # (cells, points) km
        idx = np.argpartition(d, k - 1, axis=1)[:, :k]           # k nearest, unordered
        dk = np.take_along_axis(d, idx, axis=1)
        vk, qk = values[idx], trust[idx]
        in_range = dk <= radius_km
        w = np.where(in_range, qk / np.maximum(dk, snap_km) ** power, 0.0)
        wsum = w.sum(axis=1)
        est = np.divide((w * vk).sum(axis=1), wsum, out=np.full(wsum.shape, np.nan), where=wsum > 0)
        # A cell on top of a point takes that point's value (avoids d -> 0 blow-up dominating neighbours).
        nearest = dk.argmin(axis=1)
        on_point = dk[np.arange(dk.shape[0]), nearest] < snap_km
        est[on_point] = vk[np.arange(vk.shape[0]), nearest][on_point]
        out[sl] = est
    return out


def encode_png(rgba: np.ndarray) -> bytes:
    """Minimal PNG (8-bit RGBA, no filtering) from an (H, W, 4) uint8 array. Stdlib zlib only."""
    if rgba.dtype != np.uint8 or rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("expected (H, W, 4) uint8")
    h, w, _ = rgba.shape
    raw = np.hstack([np.zeros((h, 1), np.uint8), rgba.reshape(h, w * 4)]).tobytes()  # filter byte 0 per row

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def hex_rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
