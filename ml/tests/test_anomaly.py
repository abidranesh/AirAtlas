import math
from datetime import datetime, timedelta, timezone

import numpy as np

from airatlas_ml.anomaly import detect

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
H = timedelta(hours=1)


def diurnal(days: int, base: float = 20.0, amp: float = 15.0, noise: float = 1.0, seed: int = 0) -> dict:
    """Hourly series with a strong daily cycle peaking at 18:00, like evening NO2 or PM."""
    rng = np.random.default_rng(seed)
    return {T0 + i * H: base + amp * max(0.0, math.cos(2 * math.pi * ((i % 24) - 18) / 24)) + rng.normal(0, noise)
            for i in range(days * 24)}


def test_a_regular_daily_cycle_is_not_an_anomaly():
    # 35 ug/m3 every evening is normal for this station: no alarms.
    assert detect(diurnal(14, base=20, amp=15), "pm25") == []


def test_a_spike_becomes_one_episode_with_its_peak():
    s = diurnal(14)
    for k, v in enumerate([90, 140, 120]):          # 3 h burst on day 12 at 03:00-05:00
        s[T0 + (12 * 24 + 3 + k) * H] = v
    (ep,) = detect(s, "pm25")
    assert ep.starts_at == T0 + (12 * 24 + 3) * H and ep.ends_at == T0 + (12 * 24 + 5) * H and ep.hours == 3
    assert ep.peak == 140 and ep.peak_at == T0 + (12 * 24 + 4) * H
    assert ep.z >= 4 and ep.ratio > 3 and 15 <= ep.baseline <= 25


def test_one_missing_hour_does_not_split_an_episode():
    s = diurnal(14)
    s[T0 + (12 * 24 + 3) * H] = 120
    del s[T0 + (12 * 24 + 4) * H]                   # gap
    s[T0 + (12 * 24 + 5) * H] = 130
    assert len(detect(s, "pm25")) == 1


def test_relative_jumps_in_clean_air_stay_below_the_floor():
    s = diurnal(14, base=3, amp=1, noise=0.2)        # very clean air
    s[T0 + (12 * 24 + 3) * H] = 20                  # 6x baseline, but under the 25 ug/m3 PM2.5 floor
    assert detect(s, "pm25") == []


def test_needs_a_week_of_baseline():
    s = diurnal(3)
    s[T0 + (2 * 24 + 3) * H] = 200
    assert detect(s, "pm25") == []                   # only 2 earlier days: < 10 of 21 neighbours


def test_earlier_spikes_do_not_hide_later_ones():
    """Median/MAD baseline: one past spike at the same hour must not raise the bar for the next."""
    s = diurnal(14)
    s[T0 + (10 * 24 + 3) * H] = 150
    s[T0 + (12 * 24 + 3) * H] = 150
    assert len(detect(s, "pm25")) == 2


def test_since_limits_where_episodes_may_start():
    s = diurnal(14)
    s[T0 + (9 * 24 + 3) * H] = 150
    s[T0 + (12 * 24 + 3) * H] = 150
    assert len(detect(s, "pm25", since=T0 + 11 * 24 * H)) == 1


def test_unsupported_pollutants_and_short_series_are_ignored():
    assert detect(diurnal(14), "co") == []
    assert detect({T0: 500.0}, "pm25") == []


def test_zero_baseline_has_no_ratio_instead_of_infinity():
    s = {T0 + i * H: 0.0 for i in range(14 * 24)}   # e.g. SO2 at detection limit
    s[T0 + (12 * 24 + 3) * H] = 80.0
    (ep,) = detect(s, "so2")
    assert ep.baseline == 0 and ep.ratio is None
