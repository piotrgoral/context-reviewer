"""Resolve Cursor composer.content.* snapshots from the global database."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Optional

from context_reviewer.agents.cursor.db import readonly_connection

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
        with readonly_connection(self._db_path) as conn:
            if conn is None:
                return None
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
