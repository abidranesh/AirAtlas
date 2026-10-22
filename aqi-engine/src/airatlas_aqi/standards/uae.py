"""UAE: Emirati Air Quality Index, NCM 2023 (see tables/ae_eaqi.json)."""

from collections.abc import Mapping
from datetime import datetime, timedelta

from ..averaging import HourlySeries
from ..base import AqiStandard, SubIndex, interpolate, round_half_up, truncate
from ..pollutants import Averaging, Key, Pollutant

A1, A8, A24 = Averaging.H1, Averaging.H8, Averaging.H24
O3_1H_MIN = 200  # 1-h O3 below the national standard is not used
O3_8H_MAX = 392  # above this, 1-h O3 takes over
SO2_1H_MAX = 797  # above this, 24-h SO2 takes over
SO2_FALLBACK = 200  # US-EPA TAD 2018 convention when 24-h SO2 is below its first band


class UaeEaqi(AqiStandard):
    code = "ae_eaqi"

    def _segment(self, p: Pollutant, avg: Averaging, c: float) -> tuple[float | None, bool]:
        cfg = self.spec["pollutants"][p.value]
        t = truncate(c, cfg["truncate"])
        segments = cfg["averagings"][avg.value]["segments"]
        for bp_lo, bp_hi, i_lo, i_hi in segments:
            if bp_lo <= t <= bp_hi:
                return round_half_up(interpolate(t, bp_lo, bp_hi, i_lo, i_hi)), False
        bp_lo, bp_hi, i_lo, i_hi = segments[-1]
        if t > bp_hi:  # above the top breakpoint but below the validity threshold
            return round_half_up(interpolate(t, bp_lo, bp_hi, i_lo, i_hi)), True
        return None, False

    def _sub(self, p: Pollutant, avg: Averaging, c: float) -> SubIndex | None:
        value, beyond = self._segment(p, avg, c)
        if value is None:
            return None
        return SubIndex(p, avg, c, value, self.category_for(value), beyond)

    def sub_indices(self, conc: Mapping[Key, float]) -> list[SubIndex]:
        out: list[SubIndex] = []

        # O3: max of the applicable 1-h and 8-h sub-indices.
        o3_1, o3_8 = conc.get((Pollutant.O3, A1)), conc.get((Pollutant.O3, A8))
        candidates = []
        if o3_8 is not None and (truncate(o3_8, 0) <= O3_8H_MAX or o3_1 is None):
            candidates.append(self._sub(Pollutant.O3, A8, o3_8))
        if o3_1 is not None and truncate(o3_1, 0) >= O3_1H_MIN:
            candidates.append(self._sub(Pollutant.O3, A1, o3_1))
        candidates = [c for c in candidates if c is not None]
        if not candidates and o3_8 is not None:  # 8-h > 392 with an unusable 1-h value
            candidates = [s for s in [self._sub(Pollutant.O3, A8, o3_8)] if s is not None]
        if candidates:
            out.append(max(candidates, key=lambda s: s.value))

        # SO2: 1-h up to 797, then 24-h.
        so2_1, so2_24 = conc.get((Pollutant.SO2, A1)), conc.get((Pollutant.SO2, A24))
        if so2_1 is not None and truncate(so2_1, 0) <= SO2_1H_MAX:
            out.append(self._sub(Pollutant.SO2, A1, so2_1))
        elif so2_24 is not None and truncate(so2_24, 0) > SO2_1H_MAX:
            out.append(self._sub(Pollutant.SO2, A24, so2_24))
        elif so2_1 is not None:  # 1-h above 797 but no qualifying 24-h mean
            out.append(SubIndex(Pollutant.SO2, A1, so2_1, SO2_FALLBACK, self.category_for(SO2_FALLBACK)))

        for p, avg in ((Pollutant.CO, A8), (Pollutant.NO2, A1), (Pollutant.PM10, A24), (Pollutant.PM25, A24)):
            if (p, avg) in conc and (s := self._sub(p, avg, conc[(p, avg)])) is not None:
                out.append(s)
        return out

    def from_hourly(self, hourly: Mapping[Pollutant, HourlySeries], at: datetime) -> dict[Key, float]:
        """Averages with the guideline's validation rules (Table 4 thresholds, 6/8 and 18/24 completeness)."""
        out: dict[Key, float] = {}
        for p_code, cfg in self.spec["pollutants"].items():
            p = Pollutant(p_code)
            if p not in hourly:
                continue
            limit = cfg["max_valid_hourly"]
            for avg_code, acfg in cfg["averagings"].items():
                hours = {"1h": 1, "8h": 8, "24h": 24}[avg_code]
                vals = [
                    v for k in range(hours)
                    if (v := hourly[p].get(at - timedelta(hours=k))) is not None and v <= limit
                ]
                if len(vals) >= acfg["min_valid_hours"]:
                    out[(p, Averaging(avg_code))] = sum(vals) / len(vals)
                elif vals and "national_standard" in acfg and max(vals) > acfg["national_standard"]:
                    out[(p, Averaging(avg_code))] = max(vals)  # rule VI(c)
        return out
