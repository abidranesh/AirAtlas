"""CDN cache policy. The goal is Neon's free 100 CU-hours: the database should wake ~once per
hour per URL, not once per visitor.

Live data changes when the hourly cron lands (starts :17, done by ~:25), so live responses are
cached at the CDN exactly until the next :25, then served stale for up to 10 more minutes while
one request revalidates in the background.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

from fastapi import Response

INGEST_DONE_MINUTE = 25


class Policy(Enum):
    LIVE = "live"            # latest values, series, compare
    STATUS = "status"        # system status: short, people watch it during incidents
    DAILY = "daily"          # metadata, search
    STATIC = "static"        # boundaries
    NONE = "none"


def seconds_until_next_ingest(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    nxt = now.replace(minute=INGEST_DONE_MINUTE, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(hours=1)
    return int((nxt - now).total_seconds())


def header(policy: Policy, now: datetime | None = None) -> str:
    if policy is Policy.LIVE:
        ttl = max(60, seconds_until_next_ingest(now))
        return f"public, max-age=60, s-maxage={ttl}, stale-while-revalidate=600"
    if policy is Policy.STATUS:
        return "public, max-age=30, s-maxage=60, stale-while-revalidate=60"
    if policy is Policy.DAILY:
        return "public, max-age=3600, s-maxage=86400, stale-while-revalidate=86400"
    if policy is Policy.STATIC:
        return "public, max-age=86400, s-maxage=604800, stale-while-revalidate=604800"
    return "no-store"


def apply(response: Response, policy: Policy) -> None:
    response.headers["Cache-Control"] = header(policy)
