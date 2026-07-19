"""Shared SQLite access helpers for Cursor data."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional


@contextmanager
def readonly_connection(db_path: Path) -> Iterator[Optional[sqlite3.Connection]]:
    """Open a read-only sqlite connection, or yield None if the file is missing."""
    if not db_path.exists():
        yield None
        return
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        yield conn
    finally:
        conn.close()
