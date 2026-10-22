"""Rolling means over hourly series.

Convention (shared with the database): an hourly value is keyed by the UTC
*start* of its hour. A window "ending at" hour `end` covers the starts
end-(n-1)h .. end inclusive. Missing hours are absent keys or None.
"""

from collections.abc import Mapping
from datetime import datetime, timedelta

from .pollutants import Averaging

HourlySeries = Mapping[datetime, float | None]

WINDOW_HOURS = {Averaging.H1: 1, Averaging.H8: 8, Averaging.H8_MAX24: 8, Averaging.H24: 24}


def window_values(series: HourlySeries, end: datetime, hours: int) -> list[float]:
    out = []
    for k in range(hours):
        v = series.get(end - timedelta(hours=k))
        if v is not None:
            out.append(v)
    return out


def rolling_mean(series: HourlySeries, end: datetime, hours: int, min_valid: int) -> float | None:
    vals = window_values(series, end, hours)
    if len(vals) < min_valid:
        return None
    return sum(vals) / len(vals)


def max_rolling_mean(
    series: HourlySeries, end: datetime, hours: int, span: int, min_valid: int
) -> float | None:
    """Max of the `hours`-h rolling means whose windows end within the trailing `span` hours."""
    means = [
        m
        for k in range(span - hours + 1)
        if (m := rolling_mean(series, end - timedelta(hours=k), hours, min_valid)) is not None
    ]
    return max(means) if means else None


def average(series: HourlySeries, end: datetime, averaging: Averaging, min_valid: int) -> float | None:
    if averaging is Averaging.H8_MAX24:
        return max_rolling_mean(series, end, 8, 24, min_valid)
    return rolling_mean(series, end, WINDOW_HOURS[averaging], min_valid)
