"""Phase 1 source verification: probe every data source and report coverage per region.

Usage:
    cp .env.example .env   # fill in keys
    python scripts/verify_sources.py            # all sources
    python scripts/verify_sources.py openaq     # one source

Standard library only so it runs before any project dependencies are installed.
Keys are read from the environment or a local .env file and are never printed.
"""

from __future__ import annotations

import collections
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

UA = {"User-Agent": "AirAtlas-verify/0.1 (portfolio project)"}

# Rough bounding boxes used only for discovery; ingestion filters by boundary polygons.
BBOX = {
    "tamil_nadu": (76.2, 8.0, 80.4, 13.6),
    "kerala": (74.85, 8.17, 77.42, 12.8),
    "uae": (51.5, 22.6, 56.4, 26.1),
    "germany": (5.8, 47.2, 15.1, 55.1),
}


def load_env() -> None:
    env = Path(__file__).resolve().parents[1] / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def get(url: str, headers: dict | None = None, data: bytes | None = None, retries: int = 4, timeout: int = 90):
    """GET/POST with exponential backoff; returns (status, body_text)."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2**attempt)
                continue
            return e.code, e.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def need(var: str) -> str | None:
    val = os.environ.get(var)
    if not val:
        print(f"  SKIPPED: set {var} in .env")
    return val


# --- India: CPCB via data.gov.in ---------------------------------------------
def cpcb() -> None:
    print("\n[CPCB / data.gov.in]  Tamil Nadu + Kerala")
    key = need("DATA_GOV_IN_API_KEY")
    if not key:
        return
    res = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
    for state in ("Tamil Nadu", "Kerala"):
        q = urllib.parse.urlencode({"api-key": key, "format": "json", "limit": 1000, "filters[state]": state})
        status, body = get(f"https://api.data.gov.in/resource/{res}?{q}")
        d = json.loads(body)
        recs = d.get("records", [])
        stations = {r["station"] for r in recs}
        print(f"  {state}: HTTP {status}, {len(recs)} pollutant rows (limit honoured: {d.get('limit')}), "
              f"{len(stations)} stations reporting, last_update={sorted({r['last_update'] for r in recs})[-1:]}")


# --- Germany: UBA v4 -----------------------------------------------------------
def uba() -> None:
    print("\n[UBA Air Data API v4]  Germany (no key)")
    today = datetime.now(timezone.utc).date()
    base = "https://luftdaten.umweltbundesamt.de/api/air-data/v4"
    status, body = get(f"{base}/meta/json?use=airquality&lang=en&date_from={today - timedelta(days=1)}&date_to={today}")
    meta = json.loads(body)
    st = meta["stations"].values()
    print(f"  HTTP {status}, {len(meta['stations'])} active stations")
    print(f"  by setting: {dict(collections.Counter(s[15] for s in st))}")
    print(f"  by type:    {dict(collections.Counter(s[16] for s in st))}")
    print(f"  by state:   {dict(collections.Counter(s[12] for s in st))}")


# --- Germany: EEA ----------------------------------------------------------------
def eea() -> None:
    print("\n[EEA Parquet downloads API]  Germany (no key)")
    body = json.dumps({
        "countries": ["DE"], "cities": [], "pollutants": ["PM2.5"], "dataset": 1,
        "dateTimeStart": (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%dT00:00:00Z"),
        "dateTimeEnd": datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z"),
        "aggregationType": "hour",
    }).encode()
    status, text = get("https://eeadmz1-downloads-api-appservice.azurewebsites.net/ParquetFile/urls",
                       headers={"Content-Type": "application/json"}, data=body)
    urls = [u for u in text.splitlines() if u.startswith("https://")]
    print(f"  HTTP {status}, {len(urls)} PM2.5 station parquet files for DE")


# --- OpenAQ v3 -------------------------------------------------------------------
def openaq() -> None:
    print("\n[OpenAQ v3]  all regions")
    key = need("OPENAQ_API_KEY")
    if not key:
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    for region, bbox in BBOX.items():
        q = urllib.parse.urlencode({"bbox": ",".join(map(str, bbox)), "limit": 1000})
        status, body = get(f"https://api.openaq.org/v3/locations?{q}", headers={"X-API-Key": key})
        if status != 200:
            print(f"  {region}: HTTP {status} {body[:200]}")
            continue
        locs = json.loads(body)["results"]
        active = [l for l in locs if (l.get("datetimeLast") or {}).get("utc")
                  and datetime.fromisoformat(l["datetimeLast"]["utc"].replace("Z", "+00:00")) > cutoff]
        providers = collections.Counter(l["provider"]["name"] for l in active)
        monitors = sum(1 for l in active if l.get("isMonitor"))
        print(f"  {region}: {len(locs)} locations, {len(active)} active in 7 d "
              f"({monitors} reference monitors, {len(active) - monitors} low-cost); providers: {dict(providers)}")
        time.sleep(1.1)  # stay under 60 req/min


# --- Open-Meteo ------------------------------------------------------------------
def open_meteo() -> None:
    print("\n[Open-Meteo Air Quality + Weather]  all regions (no key)")
    pts = {"Chennai": (13.08, 80.27), "Kochi": (9.93, 76.27), "Dubai": (25.2, 55.27), "Berlin": (52.52, 13.4)}
    lat = ",".join(str(p[0]) for p in pts.values())
    lon = ",".join(str(p[1]) for p in pts.values())
    status, body = get("https://air-quality-api.open-meteo.com/v1/air-quality?"
                       f"latitude={lat}&longitude={lon}&current=pm2_5,pm10,dust,european_aqi")
    for name, row in zip(pts, json.loads(body)):
        print(f"  AQ  {name}: {row['current']}")
    status, body = get("https://archive-api.open-meteo.com/v1/archive?latitude=25.2&longitude=55.27"
                       "&start_date=2024-04-16&end_date=2024-04-16&daily=precipitation_sum")
    print(f"  Historical weather (Dubai 2024-04-16 flood): HTTP {status} {json.loads(body).get('daily')}")


# --- NASA FIRMS ------------------------------------------------------------------
def firms() -> None:
    print("\n[NASA FIRMS]  fires per region (last 24 h, VIIRS S-NPP NRT)")
    key = need("FIRMS_MAP_KEY")
    if not key:
        return
    for region, bbox in BBOX.items():
        status, body = get(f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_NRT/"
                           f"{','.join(map(str, bbox))}/1")
        rows = max(0, len(body.strip().splitlines()) - 1) if status == 200 else None
        print(f"  {region}: HTTP {status}, {rows} detections")
    status, body = get(f"https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/?MAP_KEY={key}")
    print(f"  key status: {body.strip()[:200]}")


SOURCES = {"cpcb": cpcb, "uba": uba, "eea": eea, "openaq": openaq, "openmeteo": open_meteo, "firms": firms}

if __name__ == "__main__":
    load_env()
    sys.stdout.reconfigure(encoding="utf-8")
    for name in sys.argv[1:] or SOURCES:
        try:
            SOURCES[name]()
        except Exception as e:  # report and keep going: one broken source must not hide the others
            print(f"  FAILED: {type(e).__name__}: {e}")
