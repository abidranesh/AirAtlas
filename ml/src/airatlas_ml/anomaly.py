"""Robust spike detection on hourly concentrations.

For every hour t the baseline is the median of the same clock hour (±1 h) on each of the previous
7 days: 21 values. Using the same time of day keeps normal daily cycles (morning NO2 rush, afternoon
O3) out of the alarms; using the median and MAD keeps earlier spikes from inflating the baseline.

    z = (x - median) / max(1.4826 * MAD, 10% of median, MIN_SCALE)

An hour is anomalous when z >= Z_MIN, x >= 1.5 x median, and x exceeds a health-relevant floor (so
tiny bumps in very clean air are not reported). Consecutive anomalous hours, allowing a one-hour gap,
form one episode.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

METHOD = "robust_z_diurnal_v1"
Z_MIN = 4.0
RATIO_MIN = 1.5
MIN_BASELINE_VALUES = 10   # of 21
MIN_SCALE = 2.0            # ug/m3 (mg/m3 never applies: CO is not analysed)
MAX_GAP_HOURS = 1
# Values below these are never called anomalous (ug/m3; roughly 1.5x WHO 24-h guideline levels,
# and the O3 1-h level at which the EU informs sensitive people is 180).
FLOORS = {"pm25": 25.0, "pm10": 50.0, "no2": 50.0, "so2": 40.0, "o3": 120.0}
OFFSETS = np.array([-24 * d + o for d in range(1, 8) for o in (-1, 0, 1)])  # 21 neighbours


@dataclass
class Episode:
    pollutant: str
    starts_at: datetime
    ends_at: datetime
    peak_at: datetime
    peak: float
    baseline: float
    z: float
    hours: int
    values: list[float] = field(default_factory=list, repr=False)

    @property
    def ratio(self) -> float | None:
        """Peak / baseline; None when the baseline is 0 (e.g. SO2 below detection), never infinity."""
        return self.peak / self.baseline if self.baseline > 0 else None


def dense(series: dict[datetime, float]) -> tuple[datetime, np.ndarray]:
    """Hourly array from the first to the last timestamp, NaN where missing."""
    t0 = min(series)
    n = int((max(series) - t0) / timedelta(hours=1)) + 1
    arr = np.full(n, np.nan)
    for ts, v in series.items():
        arr[int((ts - t0) / timedelta(hours=1))] = v
    return t0, arr


def baseline_scale(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(median, robust scale, count of valid neighbours) for every index."""
    idx = np.arange(arr.size)[:, None] + OFFSETS[None, :]
    valid_idx = (idx >= 0) & (idx < arr.size)
    neigh = np.where(valid_idx, arr[np.clip(idx, 0, arr.size - 1)], np.nan)
    count = np.sum(~np.isnan(neigh), axis=1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN rows give NaN; `count` rules them out
        med = np.nanmedian(neigh, axis=1)
        mad = np.nanmedian(np.abs(neigh - med[:, None]), axis=1)
    scale = np.maximum.reduce([1.4826 * np.nan_to_num(mad), 0.1 * np.nan_to_num(med), np.full(arr.size, MIN_SCALE)])
    return med, scale, count


def detect(series: dict[datetime, float], pollutant: str, since: datetime | None = None) -> list[Episode]:
    """Episodes in `series` (hour-start -> value), considering only hours >= since."""
    if pollutant not in FLOORS or len(series) < 24:
        return []
    t0, arr = dense(series)
    med, scale, count = baseline_scale(arr)
    with np.errstate(invalid="ignore"):
        z = (arr - med) / scale
        hit = (
            (count >= MIN_BASELINE_VALUES)
            & (z >= Z_MIN)
            & (arr >= RATIO_MIN * med)
            & (arr >= FLOORS[pollutant])
        )
    if since is not None:
        first = max(0, int(np.ceil((since - t0) / timedelta(hours=1))))
        hit[:first] = False

    episodes: list[Episode] = []
    start = last = None
    for i in np.flatnonzero(hit):
        if start is not None and i - last <= MAX_GAP_HOURS + 1:
            last = i
            continue
        if start is not None:
            episodes.append(_episode(pollutant, t0, arr, med, z, start, last))
        start = last = i
    if start is not None:
        episodes.append(_episode(pollutant, t0, arr, med, z, start, last))
    return episodes


def _episode(pollutant, t0, arr, med, z, a, b) -> Episode:
    window = arr[a:b + 1]
    p = a + int(np.nanargmax(window))
    hour = timedelta(hours=1)
    return Episode(
        pollutant=pollutant, starts_at=t0 + a * hour, ends_at=t0 + b * hour, peak_at=t0 + p * hour,
        peak=float(arr[p]), baseline=float(med[p]), z=float(z[p]), hours=int(b - a + 1),
        values=[float(v) for v in window if not np.isnan(v)],
    )
