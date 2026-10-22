"""Vercel entrypoint (and `uvicorn app:app` locally)."""

import sys
from pathlib import Path

try:
    import airatlas_aqi  # noqa: F401  vendored copy on Vercel, or an installed package
except ImportError:  # local checkout: use the engine straight from the monorepo
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "aqi-engine" / "src"))

from airatlas_api.main import app  # noqa: E402

__all__ = ["app"]
