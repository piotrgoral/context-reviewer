"""Path helpers for Claude Code session data."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

CLAUDE_CONFIG_DIR_ENV = "CONTEXT_REVIEWER_CLAUDE_CONFIG_DIR"
UPSTREAM_CLAUDE_CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"


def get_claude_config_dir() -> Path:
    """Return Claude config root (default ``~/.claude``)."""
    for env_name in (CLAUDE_CONFIG_DIR_ENV, UPSTREAM_CLAUDE_CONFIG_DIR_ENV):
        override = os.environ.get(env_name)
        if override is not None and override.strip():
            return Path(override.strip()).expanduser()
    return Path.home() / ".claude"


def get_projects_dir(config_dir: Optional[Path] = None) -> Path:
    """Return ``projects/`` under the Claude config directory."""
    root = config_dir if config_dir is not None else get_claude_config_dir()
    return root / "projects"


def session_jsonl_path(project_dir: Path, session_id: str) -> Path:
    """Path to a session transcript JSONL file."""
    return project_dir / f"{session_id}.jsonl"


def subagents_dir(project_dir: Path, session_id: str) -> Path:
    """Directory holding subagent transcripts for a session."""
    return project_dir / session_id / "subagents"


def strip_file_uri(uri: str) -> str:
    """Decode a ``file://`` URI to a filesystem path; pass through otherwise."""
    if not uri.startswith("file://"):
        return uri
    from urllib.parse import unquote, urlparse

    return unquote(urlparse(uri).path)
