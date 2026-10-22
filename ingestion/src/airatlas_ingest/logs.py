"""Structured JSON logging. Every line carries the run context (job, region, source)."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

_context: ContextVar[dict] = ContextVar("log_context", default={})
_secrets: list[str] = []


def register_secrets(values: list[str]) -> None:
    """Values that must never appear in logs (API keys in URLs, error messages...)."""
    _secrets.extend(v for v in values if v and len(v) > 6)


def redact(text: str) -> str:
    for s in _secrets:
        text = text.replace(s, "***")
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="seconds"),
            "level": record.levelname.lower(),
            "msg": redact(record.getMessage()),
            **_context.get(),
            **{k: v for k, v in record.__dict__.get("fields", {}).items()},
        }
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str, ensure_ascii=False)


def setup(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its INFO lines would print full URLs


def bind(**fields) -> None:
    _context.set({**_context.get(), **fields})


def get(name: str) -> logging.LoggerAdapter:
    return _FieldsAdapter(logging.getLogger(name), {})


class _FieldsAdapter(logging.LoggerAdapter):
    """log.info("msg", rows=3) -> {"msg": "msg", "rows": 3, ...}"""

    def log(self, level, msg, *args, exc_info=None, **fields):
        if self.isEnabledFor(level):
            self.logger.log(level, msg, *args, exc_info=exc_info, extra={"fields": fields})

    def debug(self, msg, *a, **f): self.log(logging.DEBUG, msg, *a, **f)
    def info(self, msg, *a, **f): self.log(logging.INFO, msg, *a, **f)
    def warning(self, msg, *a, **f): self.log(logging.WARNING, msg, *a, **f)
    def error(self, msg, *a, **f): self.log(logging.ERROR, msg, *a, **f)
    def exception(self, msg, *a, **f): self.log(logging.ERROR, msg, *a, exc_info=True, **f)
