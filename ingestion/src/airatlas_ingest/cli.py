"""python -m airatlas_ingest <command> [--region R] ...

  migrate                                apply db/migrations
  boundaries [--region R]                load admin boundaries + modeled points
  hourly --region R                      measured sources (cron, hourly)
  modeled --region R                     Open-Meteo AQ + weather, FIRMS fires (cron, every 3 h)
  maintenance                            daily aggregates, retention, partitions, storage stats (cron, daily)
  backfill --region R --source S --kind K [--days N]
  backfill-events --region R             hourly data for past festival windows
  probe --region R --source S            fetch + validate without touching the database
  status                                 latest run per job/region/source
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import boundaries, db, jobs, logs
from .config import REGIONS, Settings


def _probe(settings: Settings, region_code: str, source: str) -> int:
    from .adapters.cpcb import CpcbAdapter
    from .adapters.firms import FirmsAdapter
    from .adapters.openaq import OpenAQAdapter
    from .adapters.uba import UbaAdapter

    region = REGIONS[region_code]
    rejected: Counter = Counter()
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    if source == "cpcb":
        stations, official = CpcbAdapter(settings.data_gov_in_api_key).fetch_state(region.cpcb_state, rejected)
        out = {"stations": len(stations), "official_rows": len(official)}
    elif source == "uba":
        uba = UbaAdapter()
        out = {"stations": len(uba.discover()), "readings": len(uba.hourly(now - timedelta(hours=6), now, rejected))}
    elif source == "openaq":
        stations = OpenAQAdapter(settings.openaq_api_key).discover(region.openaq_query, region.openaq_exclude_providers, rejected)
        out = {"active_locations_in_bbox": len(stations), "by_kind": Counter(s.kind for s in stations)}
    elif source == "firms":
        out = {"fires_24h": len(FirmsAdapter(settings.firms_map_key).fetch(region.id, region.bbox, rejected))}
    else:
        raise SystemExit(f"probe supports cpcb, uba, openaq, firms (got {source})")
    print(jobs.to_json({**out, "rejected": dict(rejected)}))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="airatlas_ingest", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["migrate", "boundaries", "hourly", "modeled", "maintenance", "backfill",
                                       "backfill-events", "probe", "status"])
    p.add_argument("--region", choices=sorted(REGIONS))
    p.add_argument("--source")
    p.add_argument("--kind", choices=["hourly", "daily", "weather_daily"], default="hourly")
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)

    logs.setup(args.log_level)
    settings = Settings.from_env(dry_run=args.command == "probe")
    logs.register_secrets(settings.secrets() + [settings.database_url])

    if args.command in ("hourly", "modeled", "backfill", "backfill-events", "probe") and not args.region:
        p.error(f"{args.command} needs --region")
    if args.command == "probe":
        return _probe(settings, args.region, args.source)

    region = REGIONS.get(args.region) if args.region else None
    with db.connect(settings.database_url) as conn:
        if args.command == "migrate":
            print(jobs.to_json({"applied": db.migrate(conn)}))
            return 0
        if args.command == "boundaries":
            for r in [region] if region else REGIONS.values():
                boundaries.load(conn, r)
                print(jobs.to_json({"region": r.code, "model_points": boundaries.ensure_model_points(conn, r)}))
            return 0
        if args.command == "status":
            print(jobs.to_json(jobs.status(conn)))
            return 0
        failures = {
            "hourly": lambda: jobs.hourly(conn, settings, region),
            "modeled": lambda: jobs.modeled(conn, settings, region),
            "maintenance": lambda: jobs.maintenance(conn, settings),
            "backfill": lambda: jobs.backfill(conn, settings, region, args.source, args.kind, args.days),
            "backfill-events": lambda: jobs.backfill_events(conn, settings, region),
        }[args.command]()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
