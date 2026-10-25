"""Explainable cause hints for an anomaly episode.

Each rule looks at evidence AirAtlas already stores (FIRMS fires, Open-Meteo wind/rain and modeled
dust, festival windows, other stations) and returns a hint with a confidence and the numbers behind
it. These are hints for a human, not attribution: correlation in space and time, nothing more.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime

FIRE_RADIUS_KM = 150.0
FIRE_NEAR_KM = 50.0
UPWIND_CONE_DEG = 45.0
MIN_WIND_MS = 1.0
DUST_MEDIUM, DUST_HIGH = 40.0, 100.0         # ug/m3, modeled (CAMS) dust near the station
DUST_RISE_MEDIUM, DUST_RISE_HIGH = 1.5, 2.0   # x its own 7-day median: in the UAE dust is always present
STAGNANT_WIND_MS, DRY_MM = 1.5, 0.5
REGIONAL_SHARE, REGIONAL_MIN_STATIONS = 0.3, 3
ARTEFACT_RATIO = 8.0
RANK = {"high": 0, "medium": 1, "low": 2}


@dataclass
class Hint:
    kind: str
    confidence: str
    text: str
    evidence: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class Fire:
    lat: float
    lon: float
    frp: float | None
    detected_at: datetime
    persistent: bool


@dataclass
class Context:
    lat: float
    lon: float
    pollutant: str
    station_type: str | None = None
    wind: list[tuple[float, float]] = field(default_factory=list)  # (direction FROM, deg; speed, m/s)
    precip_mm: float | None = None
    dust_max: float | None = None
    dust_baseline: float | None = None      # 7-day median dust at the same model point
    fires: list[Fire] = field(default_factory=list)
    co_stations: tuple[int, int] = (1, 1)   # (neighbours within 100 km with an overlapping episode, neighbours measuring it)
    festival: str | None = None
    hours: int = 1                           # episode length
    ratio: float | None = None               # peak / baseline


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2: 0 = north, 90 = east."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(x, y)) % 360


def angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def mean_wind(wind: list[tuple[float, float]]) -> tuple[float | None, float | None]:
    """Vector-mean direction (where the wind comes FROM) and mean speed.
    Averaging 350 deg and 10 deg must give 0 deg, not 180 deg."""
    if not wind:
        return None, None
    u = sum(s * math.sin(math.radians(d)) for d, s in wind) / len(wind)
    v = sum(s * math.cos(math.radians(d)) for d, s in wind) / len(wind)
    speed = sum(s for _, s in wind) / len(wind)
    if math.hypot(u, v) < 1e-9:
        return None, speed
    return math.degrees(math.atan2(u, v)) % 360, speed


def fire_hints(ctx: Context) -> list[Hint]:
    direction, speed = mean_wind(ctx.wind)
    near = []
    for f in ctx.fires:
        d = haversine_km(ctx.lat, ctx.lon, f.lat, f.lon)
        if d <= FIRE_RADIUS_KM:
            near.append((f, d, bearing_deg(ctx.lat, ctx.lon, f.lat, f.lon)))
    open_burning = [x for x in near if not x[0].persistent]
    persistent = [x for x in near if x[0].persistent]
    hints = []
    if direction is not None and speed is not None and speed >= MIN_WIND_MS:
        up = [x for x in open_burning if angle_diff(x[2], direction) <= UPWIND_CONE_DEG]
        if up:
            frp = sum(x[0].frp or 0 for x in up)
            # One small fire 100+ km away is weak evidence; many detections or real fire power is not.
            confidence = "high" if len(up) >= 10 or frp >= 50 else "medium" if len(up) >= 3 else "low"
            hints.append(Hint(
                "fire_upwind", confidence,
                f"{len(up)} fire detection{'s' if len(up) != 1 else ''} within {FIRE_RADIUS_KM:.0f} km upwind "
                f"(wind from {direction:.0f}°, {speed:.1f} m/s; total fire power {frp:.0f} MW)",
                {"detections": len(up), "frp_mw": round(frp, 1), "nearest_km": round(min(x[1] for x in up), 1),
                 "wind_from_deg": round(direction), "wind_ms": round(speed, 1)},
            ))
        persistent_up = [x for x in persistent if angle_diff(x[2], direction) <= UPWIND_CONE_DEG]
        if persistent_up:
            hints.append(Hint(
                "industrial_heat_upwind", "low",
                f"{len(persistent_up)} persistent heat source{'s' if len(persistent_up) != 1 else ''} upwind "
                "(likely gas flares or industry, not open burning)",
                {"detections": len(persistent_up)},
            ))
    elif open_burning:
        close = [x for x in open_burning if x[1] <= FIRE_NEAR_KM]
        if close:
            hints.append(Hint("fire_nearby", "low",
                              f"{len(close)} fire detections within {FIRE_NEAR_KM:.0f} km (wind direction unknown)",
                              {"detections": len(close)}))
    return hints


def hints_for(ctx: Context) -> list[Hint]:
    hints = fire_hints(ctx)
    if ctx.pollutant in ("pm10", "pm25") and ctx.dust_max is not None and ctx.dust_max >= DUST_MEDIUM:
        rise = ctx.dust_max / ctx.dust_baseline if ctx.dust_baseline else None
        if rise is None or rise >= DUST_RISE_MEDIUM:
            high = ctx.dust_max >= DUST_HIGH and (rise is None or rise >= DUST_RISE_HIGH)
            hints.append(Hint("dust", "high" if high else "medium",
                              f"Desert dust: modeled dust nearby peaked at {ctx.dust_max:.0f} µg/m³"
                              + (f", {rise:.1f}x its usual level" if rise else ""),
                              {"dust_max": round(ctx.dust_max, 1), **({"rise": round(rise, 2)} if rise else {})}))
    if ctx.festival and ctx.pollutant in ("pm25", "pm10", "so2"):
        hints.append(Hint("festival", "high", f"Coincides with {ctx.festival} (fireworks and bonfires)",
                          {"event": ctx.festival}))
    _, speed = mean_wind(ctx.wind)
    if speed is not None and speed < STAGNANT_WIND_MS and (ctx.precip_mm or 0) < DRY_MM:
        hints.append(Hint("stagnation", "medium", f"Stagnant air: mean wind {speed:.1f} m/s and no rain",
                          {"wind_ms": round(speed, 1), "precip_mm": round(ctx.precip_mm or 0, 1)}))
    k, n = ctx.co_stations
    if n >= REGIONAL_MIN_STATIONS and k / n >= REGIONAL_SHARE:
        hints.append(Hint("regional", "medium",
                          f"Area-wide: {k} of {n} stations within 100 km spiked within 3 h (weather or transported pollution)",
                          {"stations": k, "of": n}))
    elif n >= REGIONAL_MIN_STATIONS and k == 1:
        hints.append(Hint("local", "low", f"Local: only this station of {n} within 100 km spiked (a nearby source)", {"of": n}))
    if ctx.hours == 1 and k == 1 and ctx.ratio is not None and ctx.ratio >= ARTEFACT_RATIO:
        hints.append(Hint("possible_artefact", "low",
                          f"Single-hour spike at {ctx.ratio:.0f}x the usual level at one station only; "
                          "possibly an instrument artefact rather than pollution", {"ratio": round(ctx.ratio, 1)}))
    if ctx.pollutant == "no2" and ctx.station_type == "traffic":
        hints.append(Hint("traffic", "low", "Traffic monitoring site; NO₂ peaks track road traffic", {}))
    return sorted(hints, key=lambda h: RANK[h.confidence])
