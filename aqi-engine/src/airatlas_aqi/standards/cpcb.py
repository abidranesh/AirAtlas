"""India: CPCB National Air Quality Index (see tables/in_cpcb_naqi.json)."""

from collections.abc import Mapping

from ..base import AqiStandard, SubIndex, interpolate, round_half_up
from ..pollutants import Averaging, Key, Pollutant


def continuous_sub_index(c: float, breakpoints: list[float], index_points: list[float]) -> tuple[float, bool]:
    """Piecewise-linear sub-index as in CPCB's calculator.

    Each band starts at the previous band's upper breakpoint. Above the last
    breakpoint the slope of the last band continues. Returns (value, beyond_500).
    """
    for i in range(1, len(breakpoints)):
        if c <= breakpoints[i]:
            return interpolate(c, breakpoints[i - 1], breakpoints[i], index_points[i - 1], index_points[i]), False
    bp_lo, bp_hi = breakpoints[-2], breakpoints[-1]
    slope = (index_points[-1] - index_points[-2]) / (bp_hi - bp_lo)
    value = index_points[-1] + (c - bp_hi) * slope
    return value, value > 500


class CpcbNaqi(AqiStandard):
    code = "in_cpcb_naqi"

    def sub_indices(self, conc: Mapping[Key, float]) -> list[SubIndex]:
        points = self.spec["index_points"]
        out = []
        for p, cfg in self.spec["pollutants"].items():
            key = (Pollutant(p), Averaging(cfg["averaging"]))
            if key not in conc:
                continue
            c = conc[key]
            value, beyond = continuous_sub_index(c, cfg["breakpoints"], points)
            out.append(SubIndex(key[0], key[1], c, value, self.category_for(round_half_up(value)), beyond))
        return out
