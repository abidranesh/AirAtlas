"""Local development server: loads the repo's .env and serves the API on http://127.0.0.1:8000.

    python api/dev_server.py
"""

import os
import re
from pathlib import Path

import uvicorn

here = Path(__file__).resolve().parent
env = here.parent / ".env"
if env.exists():
    for key, value in re.findall(r"^([A-Z0-9_]+)=(.*)$", env.read_text(encoding="utf-8"), re.M):
        os.environ.setdefault(key, value.strip().strip("'\""))
os.chdir(here)

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
