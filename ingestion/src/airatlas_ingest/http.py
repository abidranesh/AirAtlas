"""HTTP with per-source rate limiting, retries and exponential backoff."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Any

import httpx

from . import logs

log = logs.get(__name__)
RETRY_STATUS = {429, 500, 502, 503, 504}


class SourceError(RuntimeError):
    """A source failed after all retries (or returned something unusable)."""


class RateLimiter:
    """Spaces requests evenly: at most `per_minute` calls per rolling minute, without bursts."""

    def __init__(self, per_minute: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.interval = 60.0 / per_minute
        self.clock, self.sleep = clock, sleep
        self._next = 0.0

    def acquire(self) -> None:
        now = self.clock()
        if now < self._next:
            self.sleep(self._next - now)
            now = self._next
        self._next = now + self.interval


class HttpClient:
    def __init__(
        self,
        source: str,
        per_minute: float,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 90.0,
        retries: int = 5,
        backoff_base: float = 2.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.source = source
        self.limiter = RateLimiter(per_minute, sleep=sleep)
        self.retries, self.backoff_base, self.sleep = retries, backoff_base, sleep
        self.calls = 0
        self._client = httpx.Client(
            headers={"User-Agent": "AirAtlas/0.1 (+https://github.com; portfolio project)", **(headers or {})},
            timeout=timeout, transport=transport, follow_redirects=True,
        )

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last: str = ""
        for attempt in range(self.retries):
            self.limiter.acquire()
            self.calls += 1
            try:
                resp = self._client.request(method, url, **kwargs)
            except httpx.TransportError as e:
                last = f"{type(e).__name__}: {e}"
            else:
                if resp.status_code not in RETRY_STATUS:
                    if resp.is_error:
                        raise SourceError(f"{self.source}: HTTP {resp.status_code} {logs.redact(resp.text[:200])}")
                    return resp
                last = f"HTTP {resp.status_code}"
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = min(float(retry_after), 120.0)
                    log.warning("rate limited, honouring Retry-After", source=self.source, wait_s=wait)
                    self.sleep(wait)
                    continue
            if attempt < self.retries - 1:
                wait = self.backoff_base * 2**attempt * (0.5 + random.random())
                log.warning("request failed, retrying", source=self.source, attempt=attempt + 1,
                            error=logs.redact(last), wait_s=round(wait, 1))
                self.sleep(wait)
        raise SourceError(f"{self.source}: giving up after {self.retries} attempts ({logs.redact(last)})")

    def get_json(self, url: str, **params: Any) -> Any:
        resp = self.request("GET", url, params=params or None)
        try:
            return resp.json()
        except ValueError as e:
            raise SourceError(f"{self.source}: invalid JSON ({resp.text[:120]!r})") from e

    def get_text(self, url: str, **params: Any) -> str:
        return self.request("GET", url, params=params or None).text

    def post_json(self, url: str, body: Any) -> httpx.Response:
        return self.request("POST", url, json=body)

    def close(self) -> None:
        self._client.close()
