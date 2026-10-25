"""India: CPCB real-time feed on data.gov.in.

The feed's min/avg/max values are CPCB SUB-INDEX values, not concentrations. Evidence: CO values
of 25-47 are impossible as mg/m3 (above 34 is already 'Severe') and far too low as ug/m3, but
normal as sub-indices. So this adapter never writes `readings`; it writes `official_aqi` and keeps
the station registry current. Raw Indian concentrations come from OpenAQ (see openaq.py).
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from .. import logs
from ..http import HttpClient, SourceError
from ..models import OfficialSubIndex, StationIn, StationKey, validate_all

log = logs.get(__name__)
URL = "https://api.data.gov.in/resource/3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
# Public sample key printed on data.gov.in. Only 10 rows per call and aggressively rate limited:
# a fallback for local experiments, not for the cron.
SAMPLE_KEY = "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b"
IST = ZoneInfo("Asia/Kolkata")
POLLUTANTS = {"PM2.5": "pm25", "PM10": "pm10", "NO2": "no2", "SO2": "so2", "CO": "co", "OZONE": "o3", "NH3": "nh3"}


def _num(v: str | None) -> float | None:
    if v in (None, "", "NA"):
        return None
    return float(v)


def parse_records(records: list[dict], rejected: Counter) -> tuple[list[StationIn], list[OfficialSubIndex]]:
    unique = {tuple(sorted(r.items())) for r in records}  # the feed repeats some rows verbatim
    if len(unique) < len(records):
        rejected["cpcb: duplicate row"] += len(records) - len(unique)
    stations: dict[str, dict] = {}
    raws = []
    for r in map(dict, unique):
        name = r["station"].strip()
        stations[name] = {"source": "cpcb", "external_id": name, "name": name, "city": r.get("city"),
                          "lat": float(r["latitude"]), "lon": float(r["longitude"]), "kind": "reference",
                          "license": "GODL-India", "meta": {"state": r.get("state")}}
        pollutant = POLLUTANTS.get(r["pollutant_id"])
        if pollutant is None:
            rejected[f"cpcb: unknown pollutant {r['pollutant_id']}"] += 1
            continue
        vals = (_num(r.get("min_value")), _num(r.get("avg_value")), _num(r.get("max_value")))
        if vals == (None, None, None):
            rejected["cpcb: NA"] += 1
            continue
        reported = datetime.strptime(r["last_update"], "%d-%m-%Y %H:%M:%S").replace(tzinfo=IST)
        raws.append({"station": StationKey(source="cpcb", external_id=name), "reported_at": reported,
                     "pollutant": pollutant, "sub_min": vals[0], "sub_avg": vals[1], "sub_max": vals[2]})
    return validate_all(StationIn, stations.values(), rejected), validate_all(OfficialSubIndex, raws, rejected)


class CpcbAdapter:
    code = "cpcb"

    def __init__(self, api_key: str | None, http: HttpClient | None = None) -> None:
        if not api_key:
            log.warning("DATA_GOV_IN_API_KEY not set; using the public sample key (10 rows/call, rate limited)")
        self.key = api_key or SAMPLE_KEY
        self.page = 1000 if api_key else 10
        # The shared sample key is throttled for everyone; long waits only hold a database connection
        # idle (Neon suspends after 5 idle minutes), so without our own key give up quickly.
        self.http = http or (HttpClient("cpcb", per_minute=20) if api_key else
                             HttpClient("cpcb", per_minute=6, retries=2, backoff_base=2.0, max_retry_after=15.0, timeout=20.0))

    def fetch_state(self, state: str, rejected: Counter) -> tuple[list[StationIn], list[OfficialSubIndex]]:
        records: list[dict] = []
        offset = 0
        while True:
            payload = self.http.get_json(URL, **{"api-key": self.key, "format": "json", "limit": self.page,
                                                 "offset": offset, "filters[state]": state})
            if "records" not in payload:
                raise SourceError(f"cpcb: unexpected response {str(payload)[:120]}")
            records += payload["records"]
            offset += self.page
            if offset >= int(payload.get("total", 0)) or not payload["records"]:
                break
        return parse_records(records, rejected)
