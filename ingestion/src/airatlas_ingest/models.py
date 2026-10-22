"""Validated records every adapter produces. Anything that fails validation is counted and dropped."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import date, datetime, timezone
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

POLLUTANTS = ("pm25", "pm10", "no2", "o3", "so2", "co", "nh3", "dust")

# Upper bounds of physically plausible hourly values in canonical units (CO in mg/m3).
# Generous on purpose: Delhi PM2.5 has exceeded 1000 ug/m3; desert dust storms push PM10 past 3000.
PLAUSIBLE_MAX = {"pm25": 2000, "pm10": 5000, "no2": 2000, "o3": 1000, "so2": 3000, "co": 150, "nh3": 3000, "dust": 10000}

StationKind = Literal["reference", "low_cost", "modeled"]


def _utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return ts.astimezone(timezone.utc)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class StationKey(_Frozen):
    source: str
    external_id: str


class StationIn(_Frozen):
    source: str
    external_id: str
    name: str = Field(min_length=1)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    kind: StationKind
    city: str | None = None
    setting: str | None = None
    station_type: str | None = None
    license: str | None = None
    meta: dict = Field(default_factory=dict)

    @property
    def key(self) -> StationKey:
        return StationKey(source=self.source, external_id=self.external_id)

    @model_validator(mode="after")
    def _not_null_island(self):
        if abs(self.lat) < 0.01 and abs(self.lon) < 0.01:
            raise ValueError("coordinates are (0, 0)")
        return self


class Reading(_Frozen):
    """One station-hour. `ts` is the hour START in UTC (minute 0, or 30 for half-hour time zones)."""

    station: StationKey
    ts: datetime
    values: dict[str, float | None]

    @field_validator("ts")
    @classmethod
    def _hour_aligned(cls, ts: datetime) -> datetime:
        ts = _utc(ts)
        if ts.second or ts.microsecond or ts.minute not in (0, 30):
            raise ValueError(f"not an hour start: {ts.isoformat()}")
        return ts

    @field_validator("values")
    @classmethod
    def _plausible(cls, values: dict[str, float]) -> dict[str, float]:
        out = {}
        for p, v in values.items():
            if p not in PLAUSIBLE_MAX:
                raise ValueError(f"unknown pollutant {p!r}")
            if v is None:
                continue
            if not 0 <= v <= PLAUSIBLE_MAX[p]:
                raise ValueError(f"{p}={v} outside 0..{PLAUSIBLE_MAX[p]}")
            out[p] = float(v)
        if not out:
            raise ValueError("no values")
        return out


class DailyReading(_Frozen):
    station: StationKey
    day: date
    means: dict[str, float]
    maxes: dict[str, float] = Field(default_factory=dict)

    @field_validator("means", "maxes")
    @classmethod
    def _plausible(cls, values: dict[str, float]) -> dict[str, float]:
        for p, v in values.items():
            if p not in PLAUSIBLE_MAX or not 0 <= v <= PLAUSIBLE_MAX[p]:
                raise ValueError(f"{p}={v} implausible")
        return values


class WeatherObs(_Frozen):
    station: StationKey
    ts: datetime
    temp_c: float | None = Field(default=None, ge=-60, le=60)
    rh_pct: float | None = Field(default=None, ge=0, le=100)
    precip_mm: float | None = Field(default=None, ge=0, le=500)
    wind_ms: float | None = Field(default=None, ge=0, le=100)
    wind_dir_deg: float | None = Field(default=None, ge=0, le=360)
    pressure_hpa: float | None = Field(default=None, ge=300, le=1100)

    @field_validator("ts")
    @classmethod
    def _to_utc(cls, ts: datetime) -> datetime:
        return _utc(ts)


class WeatherDaily(_Frozen):
    station: StationKey
    day: date
    temp_mean: float | None = Field(default=None, ge=-60, le=60)
    rh_mean: float | None = Field(default=None, ge=0, le=100)
    precip_sum: float | None = Field(default=None, ge=0, le=2000)
    wind_mean: float | None = Field(default=None, ge=0, le=100)


class OfficialSubIndex(_Frozen):
    """CPCB's published sub-index for one pollutant. An index value, not a concentration."""

    station: StationKey
    reported_at: datetime
    pollutant: str
    sub_min: float | None = Field(default=None, ge=0, le=1000)
    sub_avg: float | None = Field(default=None, ge=0, le=1000)
    sub_max: float | None = Field(default=None, ge=0, le=1000)

    @field_validator("reported_at")
    @classmethod
    def _to_utc(cls, ts: datetime) -> datetime:
        return _utc(ts)


class FireEvent(_Frozen):
    region_id: int
    detected_at: datetime
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    frp: float | None = Field(default=None, ge=0)
    confidence: str | None = None
    satellite: str
    instrument: str | None = None
    daynight: Literal["D", "N"] | None = None

    @field_validator("detected_at")
    @classmethod
    def _to_utc(cls, ts: datetime) -> datetime:
        return _utc(ts)


M = TypeVar("M", bound=BaseModel)


def validate_all(model: type[M], raws: Iterable[dict], rejected: Counter) -> list[M]:
    """Validate each raw dict; failures are tallied in `rejected` by reason, never raised."""
    out = []
    for raw in raws:
        try:
            out.append(model(**raw))
        except ValidationError as e:
            err = e.errors()[0]
            rejected[f"{model.__name__}: {err['msg'][:80]}"] += 1
    return out
