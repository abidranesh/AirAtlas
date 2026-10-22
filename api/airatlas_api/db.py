"""Connection pool shared across requests (Vercel Fluid compute reuses warm instances)."""

from __future__ import annotations

import os
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def init(url: str | None = None, search_path: str | None = None) -> ConnectionPool:
    """Open the pool lazily. min_size=0: an idle instance holds no connection, so Neon can sleep."""
    global _pool
    if _pool is None:
        def configure(conn):
            if search_path:
                conn.execute(f"set search_path to {search_path}")

        _pool = ConnectionPool(
            url or os.environ["DATABASE_URL"],
            min_size=0, max_size=4, timeout=30, max_idle=60, open=True, configure=configure,
            kwargs={"autocommit": True, "prepare_threshold": None, "row_factory": dict_row,
                    "application_name": "airatlas-api"},
        )
    return _pool


def close() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def fetch(sql: str, params: dict[str, Any] | tuple | None = None) -> list[dict]:
    with init().connection() as conn:
        return conn.execute(sql, params).fetchall()


def fetch_one(sql: str, params: dict[str, Any] | tuple | None = None) -> dict | None:
    rows = fetch(sql, params)
    return rows[0] if rows else None
