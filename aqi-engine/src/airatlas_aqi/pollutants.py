"""Pollutants, averaging periods and canonical units."""

from enum import StrEnum


class Pollutant(StrEnum):
    PM25 = "pm25"
    PM10 = "pm10"
    NO2 = "no2"
    O3 = "o3"
    SO2 = "so2"
    CO = "co"
    NH3 = "nh3"
    PB = "pb"


class Averaging(StrEnum):
    H1 = "1h"
    H8 = "8h"
    H8_MAX24 = "8h_max24"  # max 8-h rolling mean within the trailing 24 h (CPCB "max 8-hr")
    H24 = "24h"


# Every concentration entering the engine is in its pollutant's canonical unit.
# CO is mg/m3 because every standard we implement tabulates it that way.
CANONICAL_UNIT: dict[Pollutant, str] = {p: "ug/m3" for p in Pollutant} | {Pollutant.CO: "mg/m3"}

# g/mol, used for ppb <-> mass conversion of gases.
MOLECULAR_WEIGHT: dict[Pollutant, float] = {
    Pollutant.NO2: 46.0055,
    Pollutant.O3: 47.9982,
    Pollutant.SO2: 64.064,
    Pollutant.CO: 28.010,
    Pollutant.NH3: 17.031,
}

Key = tuple[Pollutant, Averaging]
