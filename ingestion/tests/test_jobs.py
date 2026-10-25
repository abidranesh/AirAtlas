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


def test_throttled_sample_key_is_a_warning_not_a_failure(monkeypatch):
    monkeypatch.setattr(jobs, "CpcbAdapter", failing_adapter("cpcb: giving up after 5 attempts (HTTP 429)"))
    r = run()
    jobs._cpcb(None, settings(None), REGIONS["tamil_nadu"], r)  # must not raise
    assert r.errors and "rate-limited" in r.errors[0]


@pytest.mark.parametrize("key, message", [
    ("own-key", "cpcb: giving up after 5 attempts (HTTP 429)"),   # our own key throttled: a real problem
    (None, "cpcb: HTTP 403 forbidden"),                            # anything other than throttling
])
def test_other_cpcb_failures_still_fail(monkeypatch, key, message):
    monkeypatch.setattr(jobs, "CpcbAdapter", failing_adapter(message))
    with pytest.raises(SourceError):
        jobs._cpcb(None, settings(key), REGIONS["kerala"], run())
