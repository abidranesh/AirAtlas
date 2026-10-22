"""Germany: Umweltbundesamt Air Data API v4 (v3 at www.umweltbundesamt.de was down on 2026-10-21)."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone

from ..http import HttpClient
from ..models import DailyReading, Reading, StationIn, StationKey, validate_all
from . import CET_FIXED

BASE = "https://luftdaten.umweltbundesamt.de/api/air-data/v4"
# component id -> pollutant. CO is already mg/m3, the rest ug/m3.
COMPONENTS = {1: "pm10", 2: "co", 3: "o3", 4: "so2", 5: "no2", 9: "pm25"}
SCOPE_HOURLY, SCOPE_DAILY = 2, 1


def parse_label(label: str) -> datetime:
    return datetime.strptime(label, "%Y-%m-%d %H:%M:%S").replace(tzinfo=CET_FIXED).astimezone(timezone.utc)


def parse_meta(payload: dict) -> list[StationIn]:
    out = []
    for v in payload["stations"].values():
        uba_id, code, name, city, active_to = v[0], v[1], v[2], v[3], v[6]
        if active_to:
            continue
        out.append(StationIn(
            source="uba", external_id=code, name=name, city=city, lat=float(v[8]), lon=float(v[7]),
            kind="reference", setting=v[15], station_type=v[16], license="dl-de/by-2-0",
            meta={"uba_id": uba_id, "network": v[12]},
        ))
    return out


def parse_measures(payload: dict, id_to_code: dict[str, str], rejected: Counter) -> list[Reading]:
    raws = []
    for uba_id, hours in payload.get("data", {}).items():
        code = id_to_code.get(str(uba_id))
        if code is None:
            rejected["uba: station not in metadata"] += len(hours)
            continue
        for start, (component, _scope, value, *_rest) in hours.items():
            pollutant = COMPONENTS.get(int(component))
            if pollutant is None or value is None:
                continue
            raws.append({"station": StationKey(source="uba", external_id=code), "ts": parse_label(start),
                         "values": {pollutant: float(value)}})
    return validate_all(Reading, raws, rejected)


def parse_daily(payload: dict, id_to_code: dict[str, str], rejected: Counter) -> list[DailyReading]:
    raws = []
    for uba_id, days in payload.get("data", {}).items():
        code = id_to_code.get(str(uba_id))
        for start, (component, _scope, value, *_rest) in days.items():
            pollutant = COMPONENTS.get(int(component))
            if code is None or pollutant is None or value is None:
                continue
            raws.append({"station": StationKey(source="uba", external_id=code), "day": date.fromisoformat(start[:10]),
                         "means": {pollutant: float(value)}})
    return validate_all(DailyReading, raws, rejected)


def _window(start_utc: datetime, end_utc: datetime) -> dict[str, str]:
    """UBA's time_from/time_to are hour-END numbers 1..24 in CET labels."""
    s = start_utc.astimezone(CET_FIXED)
    e = end_utc.astimezone(CET_FIXED)
    return {"date_from": s.date().isoformat(), "time_from": str(s.hour + 1),
            "date_to": e.date().isoformat(), "time_to": str(e.hour + 1)}


class UbaAdapter:
    code = "uba"

    def __init__(self, http: HttpClient | None = None) -> None:
        self.http = http or HttpClient("uba", per_minute=30)
        self.id_to_code: dict[str, str] = {}

    def discover(self) -> list[StationIn]:
        today = date.today()
        payload = self.http.get_json(f"{BASE}/meta/json", use="airquality", lang="en",
                                     date_from=(today - timedelta(days=1)).isoformat(), date_to=today.isoformat())
        stations = parse_meta(payload)
        self.id_to_code = {str(s.meta["uba_id"]): s.external_id for s in stations}
        return stations

    def hourly(self, start: datetime, end: datetime, rejected: Counter) -> list[Reading]:
        """All stations, all components, for [start, end] (UTC hour starts). One call per component."""
        if not self.id_to_code:
            self.discover()
        out: list[Reading] = []
        for component in COMPONENTS:
            payload = self.http.get_json(f"{BASE}/measures/json", component=component, scope=SCOPE_HOURLY,
                                         lang="en", **_window(start, end))
            out += parse_measures(payload, self.id_to_code, rejected)
        return out

    def daily(self, start: date, end: date, rejected: Counter) -> list[DailyReading]:
        if not self.id_to_code:
            self.discover()
        out: list[DailyReading] = []
        for component in COMPONENTS:
            payload = self.http.get_json(f"{BASE}/measures/json", component=component, scope=SCOPE_DAILY,
                                         lang="en", date_from=start.isoformat(), date_to=end.isoformat())
            out += parse_daily(payload, self.id_to_code, rejected)
        return out
