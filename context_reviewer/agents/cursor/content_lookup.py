"""Resolve Cursor composer.content.* snapshots from the global database."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable, Dict, Optional

ContentLookup = Callable[[str], Optional[str]]


class CursorContentLookup:
    """Fetch composer content blobs by ID, with in-memory caching."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._cache: Dict[str, Optional[str]] = {}

    def __call__(self, content_id: str) -> Optional[str]:
        if content_id in self._cache:
            return self._cache[content_id]
        content = self._fetch(content_id)
        self._cache[content_id] = content
        return content

    def _fetch(self, content_id: str) -> Optional[str]:
        if not self._db_path.exists():
            return None
        with sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT value FROM cursorDiskKV WHERE key = ?",
                (content_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        value = row[0]
        return value if isinstance(value, str) else None
