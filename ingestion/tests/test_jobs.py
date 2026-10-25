from collections import Counter
from types import SimpleNamespace

import pytest

from airatlas_ingest import jobs
from airatlas_ingest.config import REGIONS, Settings
from airatlas_ingest.http import SourceError


def settings(key):
    return Settings(database_url="", openaq_api_key=None, firms_map_key=None, data_gov_in_api_key=key, openaq_rpm=18)


def failing_adapter(message):
    class Adapter:
        def __init__(self, _key):
            pass

        def fetch_state(self, _state, _rejected):
            raise SourceError(message)

    return Adapter


def run():
    return SimpleNamespace(errors=[], rejected=Counter(), details={}, fetched=0, written=0)


@pytest.mark.parametrize("message", [
    "cpcb: giving up after 2 attempts (HTTP 429)",                 # shared key throttled
    "cpcb: giving up after 2 attempts (ConnectTimeout: timed out)",  # host unreachable from CI runners
])
def test_sample_key_failures_are_a_skipped_hour_not_a_failed_job(monkeypatch, message):
    monkeypatch.setattr(jobs, "CpcbAdapter", failing_adapter(message))
    r = run()
    jobs._cpcb(None, settings(None), REGIONS["tamil_nadu"], r)  # must not raise
    assert r.errors and "skipped this hour" in r.errors[0]


def test_with_our_own_key_failures_still_fail(monkeypatch):
    monkeypatch.setattr(jobs, "CpcbAdapter", failing_adapter("cpcb: giving up after 5 attempts (HTTP 429)"))
    with pytest.raises(SourceError):
        jobs._cpcb(None, settings("own-key"), REGIONS["kerala"], run())
