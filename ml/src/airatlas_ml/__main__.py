"""python -m airatlas_ml detect --region R [--days 10]   (all regions when --region is omitted)"""

import argparse
import sys

from airatlas_ingest import db, logs
from airatlas_ingest.config import REGIONS, Settings

from .job import detect_region


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="airatlas_ml")
    p.add_argument("command", choices=["detect"])
    p.add_argument("--region", choices=sorted(REGIONS))
    p.add_argument("--days", type=int, default=10, help="re-detect episodes ending in the last N days")
    args = p.parse_args(argv)
    logs.setup()
    settings = Settings.from_env()
    logs.register_secrets(settings.secrets() + [settings.database_url])
    failures = 0
    with db.connect(settings.database_url) as conn:
        for region in [REGIONS[args.region]] if args.region else REGIONS.values():
            try:
                with db.tracked_run(conn, "anomalies", region.code, "ml") as run:
                    run.details = detect_region(conn, region, args.days)
                    run.written = run.details["episodes"]
            except Exception:
                failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
