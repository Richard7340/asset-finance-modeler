# src/asset_finance_modeler/intelligence/benchmarks/cache.py
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

_TTL_SECONDS = 7 * 24 * 3600

_SCHEMA = """
CREATE TABLE IF NOT EXISTS benchmark_cache (
    cache_key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


class BenchmarkCache:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.executescript(_SCHEMA)

    def get(self, key: str) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value_json, created_at FROM benchmark_cache WHERE cache_key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        if time.time() - row[1] > _TTL_SECONDS:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    def set(self, key: str, value: dict) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO benchmark_cache (cache_key, value_json, created_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), time.time()),
            )
