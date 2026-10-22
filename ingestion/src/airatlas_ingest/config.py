"""Regions and settings. Adding a region starts here (see README: "Adding a region")."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"


@dataclass(frozen=True)
class BoundarySpec:
    """A geoBoundaries layer, optionally clipped to one parent unit (e.g. Indian districts inside one state)."""

    iso3: str
    adm: str                      # "ADM1" / "ADM2"
    level: str                    # admin_areas.level
    within_iso3_adm1: str | None = None   # parent layer name to clip by, e.g. "Tamil Nadu"


@dataclass(frozen=True)
class Region:
    code: str
    id: int
    name: str
    tz: ZoneInfo
    bbox: tuple[float, float, float, float]         # west, south, east, north
    boundary: BoundarySpec
    hourly_sources: tuple[str, ...]
    cpcb_state: str | None = None
    openaq_query: dict[str, str] = field(default_factory=dict)
    openaq_exclude_providers: frozenset[str] = frozenset()
    model_grid_deg: float | None = None             # extra modeled points on a grid (sparse regions)


REGIONS: dict[str, Region] = {
    r.code: r
    for r in (
        Region(
            "tamil_nadu", 1, "Tamil Nadu", ZoneInfo("Asia/Kolkata"), (76.2, 8.0, 80.4, 13.6),
            BoundarySpec("IND", "ADM2", "district", within_iso3_adm1="Tamil Nadu"),
            hourly_sources=("cpcb", "openaq"), cpcb_state="Tamil Nadu",
            openaq_query={"iso": "IN", "bbox": "76.2,8.0,80.4,13.6"},
        ),
        Region(
            "kerala", 2, "Kerala", ZoneInfo("Asia/Kolkata"), (74.85, 8.17, 77.42, 12.8),
            BoundarySpec("IND", "ADM2", "district", within_iso3_adm1="Kerala"),
            hourly_sources=("cpcb", "openaq"), cpcb_state="Kerala",
            openaq_query={"iso": "IN", "bbox": "74.85,8.17,77.42,12.8"},
        ),
        Region(
            "uae", 3, "United Arab Emirates", ZoneInfo("Asia/Dubai"), (51.5, 22.6, 56.4, 26.1),
            BoundarySpec("ARE", "ADM1", "emirate"),
            hourly_sources=("openaq",), openaq_query={"iso": "AE"}, model_grid_deg=0.75,
        ),
        Region(
            "germany", 4, "Germany", ZoneInfo("Europe/Berlin"), (5.8, 47.2, 15.1, 55.1),
            BoundarySpec("DEU", "ADM1", "state"),
            # OpenAQ is not polled for Germany: its EEA monitors duplicate UBA, and its ~209 low-cost
            # sensors would cost ~420 OpenAQ calls per hour (one per sensor), ~23 min at the shared CI
            # rate limit. UBA's 419 official stations cover Germany well without them.
            hourly_sources=("uba",), openaq_query={"iso": "DE"},
            openaq_exclude_providers=frozenset({"EEA", "Netherlands"}),
        ),
    )
}


def load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    """Minimal .env loader for local runs; CI injects secrets as real env vars."""
    if not path.exists():
        return
    for k, v in re.findall(r"^([A-Z0-9_]+)=(.*)$", path.read_text(encoding="utf-8"), re.M):
        os.environ.setdefault(k, v.strip().strip("'\""))


@dataclass(frozen=True)
class Settings:
    database_url: str
    openaq_api_key: str | None
    firms_map_key: str | None
    data_gov_in_api_key: str | None
    openaq_rpm: int      # per job; three regions share one key (60/min), so CI sets 18
    dry_run: bool = False

    @classmethod
    def from_env(cls, dry_run: bool = False) -> Settings:
        load_dotenv()
        url = os.environ.get("DATABASE_URL", "")
        if not url and not dry_run:
            raise SystemExit("DATABASE_URL is not set")
        return cls(
            database_url=url,
            openaq_api_key=os.environ.get("OPENAQ_API_KEY") or None,
            firms_map_key=os.environ.get("FIRMS_MAP_KEY") or None,
            data_gov_in_api_key=os.environ.get("DATA_GOV_IN_API_KEY") or None,
            openaq_rpm=int(os.environ.get("OPENAQ_RPM", "55")),
            dry_run=dry_run,
        )

    def secrets(self) -> list[str]:
        return [s for s in (self.openaq_api_key, self.firms_map_key, self.data_gov_in_api_key) if s]
