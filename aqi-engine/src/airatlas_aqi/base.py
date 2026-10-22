"""Common interface every AQI standard implements.

A standard is a JSON table (breakpoints, categories, sources) plus a small
class for the rules that cannot be expressed as data. Inputs are always raw
concentrations in canonical units; nothing here reads a pre-computed index.
"""

from __future__ import annotations

import json
import math
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from enum import StrEnum
from functools import cache
from importlib import resources
from typing import Any, ClassVar

from .averaging import HourlySeries, average
from .pollutants import Averaging, Key, Pollutant


# --- numeric helpers ----------------------------------------------------------------
# Decimal(repr(x)) avoids binary artefacts: truncate(60.256, 1) must be 60.2, not 60.1.
def truncate(x: float, decimals: int) -> float:
    return float(Decimal(repr(x)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_FLOOR))


def round_half_up(x: float, decimals: int = 0) -> float:
    return float(Decimal(repr(x)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP))


@cache
def load_table(code: str) -> dict[str, Any]:
    text = resources.files("airatlas_aqi").joinpath("tables", f"{code}.json").read_text(encoding="utf-8")
    return json.loads(text)


# --- result model -----------------------------------------------------------------
class Status(StrEnum):
    OK = "ok"
    PARTIAL = "partial"  # computed, but without pollutants the standard considers key
    INSUFFICIENT = "insufficient_data"


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    color: str
    level: int
    health: str
    index_range: tuple[int, int] | None = None
    health_sensitive: str | None = None


@dataclass(frozen=True)
class SubIndex:
    pollutant: Pollutant
    averaging: Averaging
    concentration: float
    value: float  # index value (index scales) or level (level scales), before final rounding
    category: Category
    beyond_scale: bool = False


@dataclass(frozen=True)
class AqiResult:
    standard: str
    status: Status
    value: int | None
    category: Category | None
    dominant: tuple[Pollutant, ...]
    sub_indices: tuple[SubIndex, ...]
    notes: tuple[str, ...] = ()
    extra: Mapping[str, float] = field(default_factory=dict)


# --- interface ----------------------------------------------------------------------
class AqiStandard(ABC):
    code: ClassVar[str]

    def __init__(self) -> None:
        self.spec = load_table(self.code)
        self.categories = tuple(
            Category(
                key=c["key"],
                label=c["label"],
                color=c["color"],
                level=c.get("level", i + 1),
                health=c["health"],
                index_range=tuple(c["index"]) if "index" in c else None,
                health_sensitive=c.get("health_sensitive"),
            )
            for i, c in enumerate(self.spec["categories"])
        )

    @property
    def name(self) -> str:
        return self.spec["name"]

    @property
    def is_index_scale(self) -> bool:
        return self.spec["scale"]["type"] == "index"

    def inputs(self) -> list[Key]:
        """(pollutant, averaging) pairs this standard consumes."""
        out = []
        for p, cfg in self.spec["pollutants"].items():
            for avg in cfg.get("averagings", {cfg.get("averaging"): None}):
                out.append((Pollutant(p), Averaging(avg)))
        return out

    @abstractmethod
    def sub_indices(self, conc: Mapping[Key, float]) -> list[SubIndex]:
        """One sub-index per pollutant available in `conc`."""

    # -- shared logic --
    def compute(self, conc: Mapping[Key, float]) -> AqiResult:
        """AQI from concentrations already averaged per the standard (canonical units)."""
        for (p, avg), v in conc.items():
            if v is None or not math.isfinite(v) or v < 0:
                raise ValueError(f"invalid concentration for {p}/{avg}: {v!r}")
        subs = self.sub_indices(conc)
        present = {s.pollutant.value for s in subs}
        notes: list[str] = []

        if len(present) < self.spec.get("min_pollutants", 1):
            notes.append(f"needs at least {self.spec['min_pollutants']} pollutants, got {len(present)}")
        required = self.spec.get("required_any") or []
        if required and not present & set(required):
            notes.append(f"needs one of: {', '.join(required)}")
        if notes or not subs:
            return AqiResult(self.code, Status.INSUFFICIENT, None, None, (), tuple(subs), tuple(notes))

        top = max(s.value for s in subs)
        value = int(round_half_up(top))
        category = self.category_for(value)
        dominant = tuple(s.pollutant for s in subs if round_half_up(s.value) == value)
        status = Status.OK
        partial_without = self.spec.get("partial_without") or []
        if partial_without and not present & set(partial_without):
            status = Status.PARTIAL
            notes.append(f"computed without {' or '.join(partial_without)}")
        return AqiResult(self.code, status, value, category, dominant, tuple(subs), tuple(notes))

    def category_for(self, value: float) -> Category:
        """Category for a (rounded) index value or a level."""
        if not self.is_index_scale:
            return self.categories[int(value) - 1]
        for c in self.categories:
            if value <= c.index_range[1]:
                return c
        return self.categories[-1]  # above the published scale

    def from_hourly(self, hourly: Mapping[Pollutant, HourlySeries], at: datetime) -> dict[Key, float]:
        """Average hourly series into the inputs this standard needs, for the hour starting `at`."""
        out: dict[Key, float] = {}
        for p, cfg in self.spec["pollutants"].items():
            series = hourly.get(Pollutant(p))
            if series is None:
                continue
            avg = Averaging(cfg["averaging"])
            v = average(series, at, avg, cfg.get("min_valid_hours", 1))
            if v is not None:
                out[(Pollutant(p), avg)] = v
        return out

    def evaluate(self, hourly: Mapping[Pollutant, HourlySeries], at: datetime) -> AqiResult:
        return self.compute(self.from_hourly(hourly, at))


class StepStandard(AqiStandard):
    """Categorical standards: concentration bands with inclusive upper bounds, no interpolation."""

    def sub_indices(self, conc: Mapping[Key, float]) -> list[SubIndex]:
        out = []
        for p, cfg in self.spec["pollutants"].items():
            key = (Pollutant(p), Averaging(cfg["averaging"]))
            if key not in conc:
                continue
            c = conc[key]
            v = c if cfg.get("round") is None else round_half_up(c, cfg["round"])
            level = next(i + 1 for i, up in enumerate(cfg["upper"]) if up is None or v <= up)
            out.append(SubIndex(key[0], key[1], c, float(level), self.category_for(level)))
        return out


def interpolate(c: float, bp_lo: float, bp_hi: float, i_lo: float, i_hi: float) -> float:
    return (i_hi - i_lo) / (bp_hi - bp_lo) * (c - bp_lo) + i_lo
