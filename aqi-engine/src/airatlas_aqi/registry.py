"""Which standard applies where. Adding a country = one table + (maybe) one class + one line here."""

from functools import cache

from .base import AqiStandard
from .standards import CpcbNaqi, EuropeanAqi, UaeEaqi, UbaLqi, WhoPm25

STANDARDS: dict[str, type[AqiStandard]] = {
    cls.code: cls for cls in (CpcbNaqi, UbaLqi, EuropeanAqi, UaeEaqi, WhoPm25)
}

# Default ("local") standard shown for each region.
LOCAL_STANDARD: dict[str, str] = {
    "tamil_nadu": "in_cpcb_naqi",
    "kerala": "in_cpcb_naqi",
    "uae": "ae_eaqi",
    "germany": "de_uba_lqi",
}

# Extra standards offered per region (Germany also shows the European AQI).
SECONDARY_STANDARDS: dict[str, tuple[str, ...]] = {"germany": ("eu_eaqi",)}

# The global toggle switches every region to one of these.
COMMON_SCALES: tuple[str, ...] = ("eu_eaqi", "who_2021_pm25")


@cache
def get_standard(code: str) -> AqiStandard:
    try:
        return STANDARDS[code]()
    except KeyError:
        raise KeyError(f"unknown AQI standard {code!r}; known: {sorted(STANDARDS)}") from None


def standard_for(region: str, scale: str = "local") -> AqiStandard:
    """`scale` is 'local' or one of COMMON_SCALES."""
    if scale == "local":
        return get_standard(LOCAL_STANDARD[region])
    if scale not in COMMON_SCALES:
        raise ValueError(f"{scale!r} is not a common scale; choose from {COMMON_SCALES}")
    return get_standard(scale)
