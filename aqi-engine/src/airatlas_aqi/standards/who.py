"""PM2.5 against the WHO 2021 guideline and interim targets (see tables/who_2021_pm25.json)."""

from collections.abc import Mapping
from dataclasses import replace

from ..base import AqiResult, StepStandard
from ..pollutants import Averaging, Key, Pollutant


class WhoPm25(StepStandard):
    code = "who_2021_pm25"

    def compute(self, conc: Mapping[Key, float]) -> AqiResult:
        result = super().compute(conc)
        pm = conc.get((Pollutant.PM25, Averaging.H24))
        if pm is None:
            return result
        return replace(result, extra={"who_multiple": pm / self.spec["guideline_multiple_of"]})
