"""SQLite-backed response cache with TTL. Prices/stock are volatile -> TTL matters."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Optional

from .config import CACHE_PATH, ensure_app_dir


class Cache:
    def __init__(self, path: Path = CACHE_PATH):
        ensure_app_dir()
        self.path = path
        self._conn = sqlite3.connect(str(path))
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT, ts REAL)"
        )
        self._conn.commit()

    def get(self, key: str, ttl_seconds: float) -> Optional[str]:
        row = self._conn.execute(
            "SELECT value, ts FROM cache WHERE key = ?", (key,)
        ).fetchone()
        if not row:
            return None
        value, ts = row
        if ttl_seconds >= 0 and (time.time() - ts) > ttl_seconds:
            return None
        return value

    def set(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, ts) VALUES (?, ?, ?)",
            (key, value, time.time()),
        )
        self._conn.commit()

    def clear(self) -> int:
        n = self._conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        self._conn.execute("DELETE FROM cache")
        self._conn.commit()
        return n

    def close(self) -> None:
        self._conn.close()
