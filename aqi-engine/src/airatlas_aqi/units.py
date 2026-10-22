"""Unit normalisation and ppb <-> mass conversion.

Mass concentration of a gas depends on the temperature and pressure the volume
is referenced to, and standards disagree: EU legislation uses 20 °C for gases,
the UAE guideline 25 °C (US-EPA convention). Callers pass the reference
conditions of the *source*; the default is 25 °C / 1013.25 hPa.
"""

from .pollutants import CANONICAL_UNIT, MOLECULAR_WEIGHT, Pollutant

R = 8.314462618  # J/(mol K)

_ALIASES = {
    "ug/m3": "ug/m3", "µg/m3": "ug/m3", "µg/m³": "ug/m3", "μg/m³": "ug/m3", "μg/m3": "ug/m3",
    "ug/m³": "ug/m3", "microgram/m3": "ug/m3",
    "mg/m3": "mg/m3", "mg/m³": "mg/m3",
    "ng/m3": "ng/m3", "ng/m³": "ng/m3",
    "ppb": "ppb", "ppm": "ppm",
}
# Mass units expressed in ug/m3, volume units in ppb.
_MASS = {"ng/m3": 1e-3, "ug/m3": 1.0, "mg/m3": 1e3}
_VOLUME = {"ppb": 1.0, "ppm": 1e3}


def normalize_unit(unit: str) -> str:
    key = unit.strip().replace(" ", "")
    try:
        return _ALIASES[key] if key in _ALIASES else _ALIASES[key.lower()]
    except KeyError:
        raise ValueError(f"unknown unit: {unit!r}") from None


def molar_volume_l(temp_c: float = 25.0, pressure_hpa: float = 1013.25) -> float:
    """Litres per mole of ideal gas (24.465 L at 25 °C, 24.055 L at 20 °C)."""
    return R * (temp_c + 273.15) / (pressure_hpa * 100) * 1000


def convert(
    value: float,
    pollutant: Pollutant,
    from_unit: str,
    to_unit: str | None = None,
    *,
    temp_c: float = 25.0,
    pressure_hpa: float = 1013.25,
) -> float:
    """Convert a concentration; `to_unit` defaults to the pollutant's canonical unit."""
    src = normalize_unit(from_unit)
    dst = normalize_unit(to_unit or CANONICAL_UNIT[pollutant])
    if src == dst:
        return value

    if src in _MASS:
        ug = value * _MASS[src]
    else:
        ug = value * _VOLUME[src] * _gas_factor(pollutant, temp_c, pressure_hpa)

    if dst in _MASS:
        return ug / _MASS[dst]
    return ug / _gas_factor(pollutant, temp_c, pressure_hpa) / _VOLUME[dst]


def _gas_factor(pollutant: Pollutant, temp_c: float, pressure_hpa: float) -> float:
    """ug/m3 per ppb."""
    if pollutant not in MOLECULAR_WEIGHT:
        raise ValueError(f"{pollutant} is not a gas; volume units do not apply")
    return MOLECULAR_WEIGHT[pollutant] / molar_volume_l(temp_c, pressure_hpa)
