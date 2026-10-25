import os
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# Resolved paths: unnormalised "ml/../x" paths can exceed Windows' 260-character limit.
for p in (ROOT / "aqi-engine" / "src", ROOT / "ingestion" / "src"):
    sys.path.insert(0, str(p))


@pytest.fixture(scope="session")
def pg():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    from airatlas_ingest import db

    conn = db.connect(url)
    schema = f"test_{uuid.uuid4().hex[:8]}"
    conn.execute(f"create schema {schema}")
    conn.execute(f"set search_path to {schema}, public")
    try:
        db.migrate(conn)
        yield conn
    finally:
        conn.execute(f"drop schema {schema} cascade")
        conn.close()
