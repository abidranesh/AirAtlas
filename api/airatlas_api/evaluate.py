"""Turn stored hourly concentrations into AQI results, honestly.

Freshness rules: a station whose newest hour is older than STALE_AFTER is flagged "stale" (still
shown, with its age); older than UNAVAILABLE_AFTER it is "unavailable" and gets no AQI at all.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

from airatlas_aqi import AqiResult, AqiStandard, Pollutant

POLLUTANTS = ("pm25", "pm10", "no2", "o3", "so2", "co", "nh3", "dust")
ENGINE_POLLUTANTS = ("pm25", "pm10", "no2", "o3", "so2", "co", "nh3")
# UBA publishes each hour ~3-4 h late (measured 2026-10-22), so "stale" starts after 5 h for monitors.
STALE_AFTER = {"reference": timedelta(hours=5), "low_cost": timedelta(hours=5), "modeled": timedelta(hours=7)}
UNAVAILABLE_AFTER = timedelta(hours=24)
HISTORY_HOURS = 32  # CPCB's max 8-h mean within the trailing 24 h reaches back 31 hours


def series_by_pollutant(rows: Iterable[dict]) -> dict[Pollutant, dict[datetime, float]]:
    out: dict[Pollutant, dict[datetime, float]] = defaultdict(dict)
    for r in rows:
        for p in ENGINE_POLLUTANTS:
            if r.get(p) is not None:
                out[Pollutant(p)][r["ts"]] = float(r[p])
    return out


def freshness(latest: datetime | None, kind: str, now: datetime) -> str:
    if latest is None or now - latest > UNAVAILABLE_AFTER:
        return "unavailable"
    return "stale" if now - latest > STALE_AFTER.get(kind, timedelta(hours=5)) else "fresh"


def category_json(cat) -> dict | None:
    if cat is None:
        return None
    return {"key": cat.key, "label": cat.label, "color": cat.color, "level": cat.level}


def result_json(std: AqiStandard, res: AqiResult) -> dict:
    return {
        "standard": std.code,
        "status": res.status.value,
        "value": res.value,
        "level": res.category.level if res.category else None,
        "category": category_json(res.category),
        "dominant": [p.value for p in res.dominant],
        "notes": list(res.notes),
        **({"extra": dict(res.extra)} if res.extra else {}),
        "sub_indices": [
            {"pollutant": s.pollutant.value, "averaging": s.averaging.value, "concentration": round(s.concentration, 2),
             "value": round(s.value, 1), "category": s.category.key, **({"beyond_scale": True} if s.beyond_scale else {})}
            for s in res.sub_indices
        ],
    }


def evaluate_station(std: AqiStandard, rows: list[dict], kind: str, now: datetime | None = None,
                     detail: bool = True) -> dict:
    """Latest AQI for one station from its recent hourly rows (sorted or not)."""
    now = now or datetime.now(timezone.utc)
    latest = max((r["ts"] for r in rows), default=None)
    fresh = freshness(latest, kind, now)
    out = {"latest_ts": latest, "age_minutes": int((now - latest).total_seconds() // 60) if latest else None,
           "freshness": fresh, "aqi": None, "concentrations": None}
    if fresh == "unavailable":
        return out
    last = next(r for r in rows if r["ts"] == latest)
    out["concentrations"] = {p: round(float(last[p]), 3) for p in POLLUTANTS if last.get(p) is not None}
    aqi = result_json(std, std.evaluate(series_by_pollutant(rows), latest))
    if not detail:  # region lists: keep payloads small; per-pollutant detail lives on the station endpoint
        aqi.pop("sub_indices"); aqi.pop("notes")
    out["aqi"] = aqi
    return out


def aqi_series(std: AqiStandard, rows: list[dict], since: datetime) -> list[dict]:
    """Hourly AQI for every hour >= since that has data (rows must include the look-back history)."""
    series = series_by_pollutant(rows)
    out = []
    for ts in sorted({r["ts"] for r in rows if r["ts"] >= since}):
        res = std.evaluate(series, ts)
        out.append({"ts": ts, "value": res.value, "level": res.category.level if res.category else None,
                    "status": res.status.value, "dominant": [p.value for p in res.dominant]})
    return out


def summarize_area(entries: list[dict]) -> dict | None:
    """Area colour: median of its measured stations with a usable AQI; else its model point(s).

    Median, not worst: one roadside monitor should not paint a whole district red. The basis is
    returned so the UI can label modeled areas as modeled.
    """
    usable = [e for e in entries if e["aqi"] and e["aqi"]["value"] is not None and e["freshness"] != "unavailable"]
    measured = [e for e in usable if e["kind"] != "modeled"]
    basis, pool = ("measured", measured) if measured else ("modeled", [e for e in usable if e["kind"] == "modeled"])
    if not pool:
        return None
    values = sorted(e["aqi"]["value"] for e in pool)
    return {"value": int(statistics.median_low(values)), "basis": basis, "n_stations": len(pool)}
