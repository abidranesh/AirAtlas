import json
import os
import sys
import uuid
from collections import Counter
from pathlib import Path

import pytest

# Resolved (not "ingestion/../aqi-engine"): unnormalised paths can exceed Windows' 260-char limit.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "aqi-engine" / "src"))

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    path = FIXTURES / name
    return path.read_text(encoding="utf-8") if path.suffix == ".csv" else json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def rejected() -> Counter:
    return Counter()


@pytest.fixture(scope="session")
def pg():
    """A migrated, throwaway schema. Set TEST_DATABASE_URL to a Postgres with PostGIS available.
    Use a direct (non-pooled) connection: the test relies on a session-level search_path."""
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
