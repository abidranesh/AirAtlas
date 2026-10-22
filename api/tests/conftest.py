import os
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# Resolved paths: unnormalised "api/../x" paths can exceed Windows' 260-character limit.
for p in (ROOT / "aqi-engine" / "src", ROOT / "ingestion" / "src"):
    sys.path.insert(0, str(p))


@pytest.fixture(scope="session")
def schema_url():
    """A migrated throwaway schema; yields (url, schema). Needs TEST_DATABASE_URL (direct, non-pooled)."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    from airatlas_ingest import db as ingest_db

    conn = ingest_db.connect(url)
    schema = f"test_{uuid.uuid4().hex[:8]}"
    conn.execute(f"create schema {schema}")
    conn.execute(f"set search_path to {schema}, public")
    try:
        ingest_db.migrate(conn)
        yield conn, url, schema
    finally:
        conn.execute(f"drop schema {schema} cascade")
        conn.close()
