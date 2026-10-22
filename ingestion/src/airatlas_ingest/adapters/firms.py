"""NASA FIRMS active fires (VIIRS on Suomi-NPP and NOAA-20), near-real-time."""

from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import date, datetime, timezone

from ..http import HttpClient, SourceError
from ..models import FireEvent, validate_all

URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{product}/{bbox}/{days}"
PRODUCTS = ("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT")
MAX_DAYS = 5   # per request (FIRMS limit)
MARGIN_DEG = 1.0  # fires just outside a region can still drive its air quality


def parse_csv(text: str, region_id: int, rejected: Counter) -> list[FireEvent]:
    if not text.startswith("latitude"):
        raise SourceError(f"firms: unexpected response {text[:100]!r}")
    raws = []
    for r in csv.DictReader(io.StringIO(text)):
        t = r["acq_time"].zfill(4)  # HHMM, UTC
        raws.append({
            "region_id": region_id,
            "detected_at": datetime.strptime(f"{r['acq_date']} {t}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc),
            "lat": float(r["latitude"]), "lon": float(r["longitude"]),
            "frp": float(r["frp"]) if r.get("frp") else None, "confidence": r.get("confidence"),
            "satellite": r["satellite"], "instrument": r.get("instrument"), "daynight": r.get("daynight") or None,
        })
    return validate_all(FireEvent, raws, rejected)


class FirmsAdapter:
    code = "firms"

    def __init__(self, map_key: str, http: HttpClient | None = None) -> None:
        if not map_key:
            raise ValueError("FIRMS_MAP_KEY is required")
        self.key = map_key
        self.http = http or HttpClient("firms", per_minute=30)

    def fetch(self, region_id: int, bbox: tuple[float, float, float, float], rejected: Counter,
              days: int = 1, start: date | None = None) -> list[FireEvent]:
        w, s, e, n = bbox
        area = f"{w - MARGIN_DEG},{s - MARGIN_DEG},{e + MARGIN_DEG},{n + MARGIN_DEG}"
        out: list[FireEvent] = []
        for product in PRODUCTS:
            url = URL.format(key=self.key, product=product, bbox=area, days=min(days, MAX_DAYS))
            if start:
                url += f"/{start.isoformat()}"
            out += parse_csv(self.http.get_text(url), region_id, rejected)
        return out
