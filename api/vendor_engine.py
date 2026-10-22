"""Vercel build step: copy the AQI engine package next to app.py so the function bundle contains it.

The engine has no dependencies, so vendoring one directory is simpler and more predictable than a
path dependency in a monorepo build. The copy is git-ignored; the source of truth stays in aqi-engine/.
"""

import shutil
from pathlib import Path

here = Path(__file__).resolve().parent
src = here.parent / "aqi-engine" / "src" / "airatlas_aqi"
dst = here / "airatlas_aqi"
if dst.exists():
    shutil.rmtree(dst)
shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
print(f"vendored {src} -> {dst}")
