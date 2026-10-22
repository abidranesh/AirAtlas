from collections import Counter
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from airatlas_ingest import logs
from airatlas_ingest.http import HttpClient, RateLimiter, SourceError
from airatlas_ingest.models import Reading, StationIn, StationKey, validate_all

K = StationKey(source="uba", external_id="DEBB021")
UTC = timezone.utc


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.sleeps: list[float] = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def client(handler, **kw):
    clock = FakeClock()
    return HttpClient("test", per_minute=6000, transport=httpx.MockTransport(handler), sleep=clock.sleep, **kw), clock


class TestRateLimiter:
    def test_spaces_calls_evenly(self):
        clock = FakeClock()
        rl = RateLimiter(per_minute=60, clock=clock, sleep=clock.sleep)
        for _ in range(4):
            rl.acquire()
        assert clock.sleeps == [1.0, 1.0, 1.0]  # first call immediate, then 1 s apart

    def test_no_wait_when_calls_are_already_slow(self):
        clock = FakeClock()
        rl = RateLimiter(per_minute=60, clock=clock, sleep=clock.sleep)
        rl.acquire()
        clock.t += 5
        rl.acquire()
        assert clock.sleeps == []


class TestRetries:
    def test_honours_retry_after_then_succeeds(self):
        calls = []

        def handler(req):
            calls.append(req)
            if len(calls) == 1:
                return httpx.Response(429, headers={"Retry-After": "7"})
            return httpx.Response(200, json={"ok": True})

        c, clock = client(handler)
        assert c.get_json("https://x.test/a") == {"ok": True}
        assert 7.0 in clock.sleeps and c.calls == 2

    def test_backs_off_exponentially_on_5xx_then_gives_up(self):
        c, clock = client(lambda req: httpx.Response(503), retries=4, backoff_base=1.0)
        with pytest.raises(SourceError, match="giving up after 4"):
            c.get_json("https://x.test/a")
        waits = [s for s in clock.sleeps if s > 0.05]
        assert len(waits) == 3 and waits[0] < waits[-1]  # 1x, 2x, 4x base (with jitter)

    def test_client_errors_are_not_retried(self):
        c, _ = client(lambda req: httpx.Response(404, text="nope"))
        with pytest.raises(SourceError, match="HTTP 404"):
            c.get_json("https://x.test/a")
        assert c.calls == 1

    def test_transport_errors_are_retried(self):
        n = {"i": 0}

        def handler(req):
            n["i"] += 1
            if n["i"] < 3:
                raise httpx.ConnectError("boom")
            return httpx.Response(200, json=[1])

        c, _ = client(handler)
        assert c.get_json("https://x.test/a") == [1]

    def test_secrets_are_redacted_from_errors(self):
        logs.register_secrets(["supersecretkey123"])
        c, _ = client(lambda req: httpx.Response(403, text="bad key supersecretkey123"))
        with pytest.raises(SourceError) as e:
            c.get_json("https://x.test/a")
        assert "supersecretkey123" not in str(e.value)


class TestModels:
    def test_reading_normalises_to_utc_and_accepts_half_hour_zones(self):
        ist = timezone(timedelta(hours=5, minutes=30))
        r = Reading(station=K, ts=datetime(2026, 10, 21, 6, 0, tzinfo=ist), values={"pm25": 12})
        assert r.ts == datetime(2026, 10, 21, 0, 30, tzinfo=UTC)

    @pytest.mark.parametrize(
        "ts, values, reason",
        [
            (datetime(2026, 1, 1), {"pm25": 1}, "timezone-aware"),
            (datetime(2026, 1, 1, 0, 15, tzinfo=UTC), {"pm25": 1}, "not an hour start"),
            (datetime(2026, 1, 1, tzinfo=UTC), {"pm25": -3}, "outside"),
            (datetime(2026, 1, 1, tzinfo=UTC), {"co": 900}, "outside"),  # CO is mg/m3: 900 is a unit bug
            (datetime(2026, 1, 1, tzinfo=UTC), {"benzene": 1}, "unknown pollutant"),
            (datetime(2026, 1, 1, tzinfo=UTC), {"pm25": None}, "no values"),
        ],
    )
    def test_invalid_readings_are_counted_not_raised(self, ts, values, reason):
        rejected = Counter()
        assert validate_all(Reading, [{"station": K, "ts": ts, "values": values}], rejected) == []
        assert reason in next(iter(rejected))

    def test_null_island_station_rejected(self):
        rejected = Counter()
        validate_all(StationIn, [{"source": "x", "external_id": "1", "name": "n", "lat": 0, "lon": 0, "kind": "reference"}], rejected)
        assert sum(rejected.values()) == 1
