"""Festival windows whose HOURLY data is kept forever (readings_archive) for the insight pages.

Each window is +-3 days around the local date. Dates come from public holiday calendars and are
listed explicitly so they can be reviewed. `verified` = checked against an official list; the
+-3-day window tolerates a one-day error until then.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .config import REGIONS

WINDOW_DAYS = 3


@dataclass(frozen=True)
class Event:
    label: str
    regions: tuple[str, ...]
    day: date
    verified: bool = False

    def window(self, region: str) -> tuple[datetime, datetime]:
        tz = REGIONS[region].tz
        start = datetime.combine(self.day - timedelta(days=WINDOW_DAYS), time(0), tz)
        end = datetime.combine(self.day + timedelta(days=WINDOW_DAYS + 1), time(0), tz)
        return start, end


INDIA = ("tamil_nadu", "kerala")
EVENTS: list[Event] = [
    *(Event(f"deepavali_{d.year}", INDIA, d) for d in (
        date(2022, 10, 24), date(2023, 11, 12), date(2024, 10, 31), date(2025, 10, 20), date(2026, 11, 8))),
    *(Event(f"bhogi_{d.year}", ("tamil_nadu",), d) for d in (
        date(2023, 1, 14), date(2024, 1, 14), date(2025, 1, 13), date(2026, 1, 13))),
    *(Event(f"new_years_eve_{y}", ("germany", "uae"), date(y, 12, 31), verified=True) for y in range(2022, 2027)),
]
