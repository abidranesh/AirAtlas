"""European Environment Agency parquet downloads: secondary source for Germany.

Used only by backfill, to fill hours UBA lacks (EEA has lower priority, so it never overwrites
UBA values). Station codes match UBA's (SPO.DE_DEBB021_... <-> DEBB021). Needs `pip install
airatlas-ingest[eea]` (pyarrow).
"""

from __future__ import annotations

import io
import re
from collections import Counter
from datetime import datetime, timezone

from ..http import HttpClient
from ..models import Reading, StationKey, validate_all
from . import CET_FIXED

URLS = "https://eeadmz1-downloads-api-appservice.azurewebsites.net/ParquetFile/urls"
POLLUTANTS = {"PM2.5": "pm25", "PM10": "pm10", "NO2": "no2", "O3": "o3", "SO2": "so2", "CO": "co"}
CODES = {6001: "pm25", 5: "pm10", 8: "no2", 7: "o3", 1: "so2", 10: "co"}
VALID = {1, 2, 3}  # 1 valid, 2 valid below detection limit, 3 valid (substituted LOD/2)
STATION_RE = re.compile(r"SPO\.DE_(DE[A-Z]{2}\d{3})_")


def parse_table(rows: list[dict], rejected: Counter) -> list[Reading]:
    raws = []
    for r in rows:
        m = STATION_RE.search(r["Samplingpoint"])
        p = CODES.get(r["Pollutant"])
        if not m or p is None or r["AggType"] != "hour":
            continue
        if r["Validity"] not in VALID or r["Value"] is None:
            rejected["eea: invalid or placeholder"] += 1
            continue
        value = float(r["Value"])
        if p == "co" and r["Unit"].startswith("ug"):
            value /= 1000
        start = r["Start"].replace(tzinfo=CET_FIXED).astimezone(timezone.utc)
        raws.append({"station": StationKey(source="uba", external_id=m.group(1)), "ts": start, "values": {p: value}})
    return validate_all(Reading, raws, rejected)


class EeaAdapter:
    code = "eea"

    def __init__(self, http: HttpClient | None = None) -> None:
        self.http = http or HttpClient("eea", per_minute=60)

    def hourly(self, start: datetime, end: datetime, pollutants: list[str], rejected: Counter,
               station_codes: set[str] | None = None) -> list[Reading]:
        import pyarrow.parquet as pq  # optional dependency

        body = {"countries": ["DE"], "cities": [], "pollutants": pollutants, "dataset": 1,
                "dateTimeStart": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "dateTimeEnd": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "aggregationType": "hour"}
        urls = [u for u in self.http.post_json(URLS, body).text.splitlines() if u.startswith("https://")]
        out: list[Reading] = []
        for url in urls:
            m = STATION_RE.search(url)
            if station_codes is not None and (not m or m.group(1) not in station_codes):
                continue
            table = pq.read_table(io.BytesIO(self.http.request("GET", url).content))
            lo, hi = start.astimezone(CET_FIXED).replace(tzinfo=None), end.astimezone(CET_FIXED).replace(tzinfo=None)
            rows = [r for r in table.to_pylist() if lo <= r["Start"] <= hi]
            out += parse_table(rows, rejected)
        return out
