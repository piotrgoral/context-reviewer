"""Shared path/URI helpers for Cursor data."""

from __future__ import annotations

from urllib.parse import unquote, urlparse


def strip_file_uri(uri: str) -> str:
    """Decode a ``file://`` URI to a filesystem path; pass through otherwise."""
    if not uri.startswith("file://"):
        return uri
    return unquote(urlparse(uri).path)
