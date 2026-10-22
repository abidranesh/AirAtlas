"""Open-Meteo: modeled air quality (CAMS, incl. dust) and weather for model grid points.

Free tier: 10,000 calls/day, and every location in a multi-location request counts as a call.
So modeled data is fetched every 3 h (not hourly), with an overlapping past window.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone

from ..http import HttpClient
from ..models import Reading, StationKey, WeatherDaily, WeatherObs, validate_all

AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WX_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
AQ_VARS = {"pm2_5": "pm25", "pm10": "pm10", "nitrogen_dioxide": "no2", "ozone": "o3",
           "sulphur_dioxide": "so2", "carbon_monoxide": "co", "dust": "dust"}
WX_VARS = {"temperature_2m": "temp_c", "relative_humidity_2m": "rh_pct", "precipitation": "precip_mm",
           "wind_speed_10m": "wind_ms", "wind_direction_10m": "wind_dir_deg", "surface_pressure": "pressure_hpa"}
WX_DAILY_VARS = {"temperature_2m_mean": "temp_mean", "relative_humidity_2m_mean": "rh_mean",
                 "precipitation_sum": "precip_sum", "wind_speed_10m_mean": "wind_mean"}
CHUNK = 50  # locations per request (URL length)


def _as_list(payload) -> list[dict]:
    return payload if isinstance(payload, list) else [payload]


def _hour(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def parse_aq(payload, keys: list[StationKey], not_after: datetime, rejected: Counter) -> list[Reading]:
    raws = []
    for key, loc in zip(keys, _as_list(payload), strict=True):
        h = loc["hourly"]
        for i, t in enumerate(h["time"]):
            ts = _hour(t)
            if ts > not_after:  # skip forecast hours; only analysed/past hours are stored
                continue
            vals = {}
            for var, p in AQ_VARS.items():
                v = h.get(var, [None] * len(h["time"]))[i]
                if v is not None:
                    vals[p] = v / 1000 if p == "co" else v  # CO ug/m3 -> mg/m3
            if vals:
                raws.append({"station": key, "ts": ts, "values": vals})
    return validate_all(Reading, raws, rejected)


def parse_weather(payload, keys: list[StationKey], not_after: datetime, rejected: Counter) -> list[WeatherObs]:
    raws = []
    for key, loc in zip(keys, _as_list(payload), strict=True):
        h = loc["hourly"]
        for i, t in enumerate(h["time"]):
            ts = _hour(t)
            if ts <= not_after:
                raws.append({"station": key, "ts": ts, **{col: h[var][i] for var, col in WX_VARS.items() if var in h}})
    return validate_all(WeatherObs, raws, rejected)


def parse_weather_daily(payload, keys: list[StationKey], rejected: Counter) -> list[WeatherDaily]:
    raws = []
    for key, loc in zip(keys, _as_list(payload), strict=True):
        d = loc["daily"]
        for i, day in enumerate(d["time"]):
            raws.append({"station": key, "day": date.fromisoformat(day),
                         **{col: d[var][i] for var, col in WX_DAILY_VARS.items() if var in d}})
    return validate_all(WeatherDaily, raws, rejected)


class OpenMeteoAdapter:
    code = "open_meteo"

    def __init__(self, http: HttpClient | None = None) -> None:
        self.http = http or HttpClient("open_meteo", per_minute=60)

    @staticmethod
    def _coords(points: list[tuple[StationKey, float, float]]) -> dict[str, str]:
        return {"latitude": ",".join(f"{p[1]:.4f}" for p in points),
                "longitude": ",".join(f"{p[2]:.4f}" for p in points)}

    def _chunks(self, points):
        for i in range(0, len(points), CHUNK):
            yield points[i:i + CHUNK]

    def air_quality(self, points: list[tuple[StationKey, float, float]], rejected: Counter, *,
                    past_hours: int | None = None, start: date | None = None, end: date | None = None) -> list[Reading]:
        now = datetime.now(timezone.utc)
        window = {"past_hours": past_hours, "forecast_hours": 1} if past_hours else {"start_date": start.isoformat(), "end_date": end.isoformat()}
        out: list[Reading] = []
        for chunk in self._chunks(points):
            payload = self.http.get_json(AQ_URL, hourly=",".join(AQ_VARS), timezone="GMT", **window, **self._coords(chunk))
            out += parse_aq(payload, [p[0] for p in chunk], now, rejected)
        return out

    def weather(self, points: list[tuple[StationKey, float, float]], rejected: Counter, *,
                past_hours: int | None = None, start: date | None = None, end: date | None = None) -> list[WeatherObs]:
        now = datetime.now(timezone.utc)
        window = {"past_hours": past_hours, "forecast_hours": 1} if past_hours else {"start_date": start.isoformat(), "end_date": end.isoformat()}
        out: list[WeatherObs] = []
        for chunk in self._chunks(points):
            payload = self.http.get_json(WX_URL, hourly=",".join(WX_VARS), timezone="GMT", wind_speed_unit="ms",
                                         **window, **self._coords(chunk))
            out += parse_weather(payload, [p[0] for p in chunk], now, rejected)
        return out

    def weather_daily(self, points: list[tuple[StationKey, float, float]], tz: str, start: date, end: date,
                      rejected: Counter) -> list[WeatherDaily]:
        """ERA5 archive, aggregated by Open-Meteo to the region's LOCAL calendar day."""
        out: list[WeatherDaily] = []
        for chunk in self._chunks(points):
            payload = self.http.get_json(ARCHIVE_URL, daily=",".join(WX_DAILY_VARS), timezone=tz, wind_speed_unit="ms",
                                         start_date=start.isoformat(), end_date=end.isoformat(), **self._coords(chunk))
            out += parse_weather_daily(payload, [p[0] for p in chunk], rejected)
        return out
