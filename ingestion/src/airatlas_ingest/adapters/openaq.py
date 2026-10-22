"""OpenAQ v3: Indian CPCB monitors (hourly concentrations), UAE and German low-cost sensors.

Data-quality rules applied here:
- an hour is kept only if OpenAQ reports >= 75% of its expected sub-hourly measurements;
- units are converted to canonical units (gases at 25 C, the convention of CPCB/US-EPA);
- CPCB CO labelled "ppb" with values < 20 is really mg/m3 (CPCB's native unit): ambient CO is
  ~100-2000 ppb, so 0.2-0.5 "ppb" is a mislabel. Such values are corrected and counted.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone

from airatlas_aqi import Pollutant, convert
from airatlas_aqi.units import normalize_unit

from .. import logs
from ..http import HttpClient
from ..models import DailyReading, Reading, StationIn, StationKey, validate_all

log = logs.get(__name__)
BASE = "https://api.openaq.org/v3"
PARAMETERS = {"pm25", "pm10", "no2", "o3", "so2", "co", "nh3"}
MIN_COVERAGE_PCT = 75.0
CO_PPB_IMPLAUSIBLE_BELOW = 20.0


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def parse_locations(results: list[dict], exclude_providers: frozenset[str], active_since: datetime,
                    rejected: Counter) -> list[StationIn]:
    raws = []
    for loc in results:
        last = (loc.get("datetimeLast") or {}).get("utc")
        if loc.get("isMobile") or loc["provider"]["name"] in exclude_providers:
            continue
        if not last or _ts(last) < active_since:
            continue
        sensors = {str(s["id"]): [s["parameter"]["name"], s["parameter"]["units"]]
                   for s in loc["sensors"] if s["parameter"]["name"] in PARAMETERS}
        if not sensors:
            continue
        raws.append({
            "source": "openaq", "external_id": str(loc["id"]), "name": loc["name"], "city": loc.get("locality"),
            "lat": loc["coordinates"]["latitude"], "lon": loc["coordinates"]["longitude"],
            "kind": "reference" if loc.get("isMonitor") else "low_cost",
            "license": ((loc.get("licenses") or [{}])[0] or {}).get("name"),
            "meta": {"sensors": sensors, "provider": loc["provider"]["name"], "datetime_last": last},
        })
    return validate_all(StationIn, raws, rejected)


def to_canonical(parameter: str, value: float, units: str, rejected: Counter) -> float:
    unit = normalize_unit(units)
    pollutant = Pollutant(parameter)
    if pollutant is Pollutant.CO and unit == "ppb" and value < CO_PPB_IMPLAUSIBLE_BELOW:
        rejected["openaq: CO 'ppb' relabelled mg/m3 (corrected, kept)"] += 1
        unit = "mg/m3"
    return convert(value, pollutant, unit, temp_c=25.0)


def parse_hours(results: list[dict], station: StationKey, parameter: str, units: str,
                rejected: Counter) -> list[Reading]:
    raws = []
    for row in results:
        cov = (row.get("coverage") or {}).get("percentCoverage")
        if cov is not None and cov < MIN_COVERAGE_PCT:
            rejected["openaq: hour below 75% coverage"] += 1
            continue
        if row.get("value") is None:
            continue
        raws.append({"station": station, "ts": _ts(row["period"]["datetimeFrom"]["utc"]),
                     "values": {parameter: to_canonical(parameter, row["value"], units, rejected)}})
    return validate_all(Reading, raws, rejected)


def parse_days(results: list[dict], station: StationKey, parameter: str, units: str,
               rejected: Counter) -> list[DailyReading]:
    raws = []
    for row in results:
        cov = (row.get("coverage") or {}).get("percentCoverage")
        if row.get("value") is None or (cov is not None and cov < MIN_COVERAGE_PCT):
            rejected["openaq: day below 75% coverage"] += 1
            continue
        day = date.fromisoformat(row["period"]["datetimeFrom"]["local"][:10])
        mx = (row.get("summary") or {}).get("max")
        raws.append({"station": station, "day": day,
                     "means": {parameter: to_canonical(parameter, row["value"], units, rejected)},
                     "maxes": {parameter: to_canonical(parameter, mx, units, rejected)} if mx is not None else {}})
    return validate_all(DailyReading, raws, rejected)


class OpenAQAdapter:
    code = "openaq"

    def __init__(self, api_key: str, per_minute: float = 55, http: HttpClient | None = None) -> None:
        if not api_key:
            raise ValueError("OPENAQ_API_KEY is required")
        self.http = http or HttpClient("openaq", per_minute=per_minute, headers={"X-API-Key": api_key})

    def _pages(self, path: str, **params) -> Iterator[list[dict]]:
        page = 1
        while True:
            payload = self.http.get_json(f"{BASE}/{path}", limit=1000, page=page, **params)
            results = payload.get("results", [])
            yield results
            if len(results) < 1000:
                return
            page += 1

    def discover(self, query: dict[str, str], exclude_providers: frozenset[str], rejected: Counter) -> list[StationIn]:
        since = datetime.now(timezone.utc) - timedelta(days=30)
        out: list[StationIn] = []
        for results in self._pages("locations", **query):
            out += parse_locations(results, exclude_providers, since, rejected)
        return out

    def hours(self, sensor_id: str, parameter: str, units: str, station: StationKey,
              start: datetime, end: datetime, rejected: Counter) -> list[Reading]:
        out: list[Reading] = []
        for results in self._pages(f"sensors/{sensor_id}/hours",
                                   datetime_from=start.isoformat(), datetime_to=end.isoformat()):
            out += parse_hours(results, station, parameter, units, rejected)
        return out

    def days(self, sensor_id: str, parameter: str, units: str, station: StationKey,
             start: date, end: date, rejected: Counter) -> list[DailyReading]:
        out: list[DailyReading] = []
        for results in self._pages(f"sensors/{sensor_id}/days",
                                   datetime_from=start.isoformat(), datetime_to=end.isoformat()):
            out += parse_days(results, station, parameter, units, rejected)
        return out
