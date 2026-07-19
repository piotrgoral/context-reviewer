"""Scan Claude Code project/session directories and read session metadata."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_META_PREFIXES = (
    "<command-name>",
    "<local-command-caveat>",
    "<task-notification>",
    "<task-reminder>",
)


def is_meta_user_content(text: str) -> bool:
    """Return True if a user string line is system/meta, not a real prompt."""
    stripped = text.strip()
    if not stripped:
        return True
    return stripped.startswith(_META_PREFIXES)


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _timestamp_ms(value: Any) -> int:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def read_session_metadata(session_path: Path) -> Dict[str, Any]:
    """
    Scan a session JSONL file for listing metadata.

    Returns dict with session_id, title, slug, cwd, git_branch, last_updated_ms.
    """
    session_id = session_path.stem
    title: Optional[str] = None
    slug: Optional[str] = None
    cwd: Optional[str] = None
    git_branch: Optional[str] = None
    last_updated_ms = 0

    try:
        with open(session_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not isinstance(record, dict):
                    continue

                line_type = record.get("type")
                if line_type == "ai-title":
                    candidate = record.get("aiTitle")
                    if isinstance(candidate, str) and candidate.strip():
                        title = candidate.strip()
                elif line_type == "assistant" or line_type == "user":
                    candidate = record.get("slug")
                    if isinstance(candidate, str) and candidate.strip():
                        slug = candidate.strip()
                    candidate = record.get("cwd")
                    if isinstance(candidate, str) and candidate.strip():
                        cwd = candidate.strip()
                    candidate = record.get("gitBranch")
                    if isinstance(candidate, str) and candidate.strip():
                        git_branch = candidate.strip()

                ts = _timestamp_ms(record.get("timestamp"))
                if ts > last_updated_ms:
                    last_updated_ms = ts
    except OSError:
        pass

    display_name = title or slug or session_id[:8]
    return {
        "session_id": session_id,
        "name": display_name,
        "title": title,
        "slug": slug,
        "cwd": cwd or "",
        "git_branch": git_branch,
        "lastUpdatedAt": last_updated_ms,
        "session_path": str(session_path),
    }


def _project_name_from_cwd(cwd: str) -> str:
    if not cwd:
        return "unknown"
    return os.path.basename(os.path.normpath(cwd)) or cwd


def scan_project_dir(project_dir: Path) -> Tuple[str, str, List[Dict[str, Any]]]:
    """
    Scan one encoded project directory for session JSONL files.

    Returns (project_name, folder_path, sessions).
    """
    sessions: List[Dict[str, Any]] = []
    folder_path = ""
    project_name = project_dir.name

    for session_path in sorted(project_dir.glob("*.jsonl")):
        if not session_path.is_file():
            continue
        meta = read_session_metadata(session_path)
        sessions.append(meta)
        if meta.get("cwd") and not folder_path:
            folder_path = meta["cwd"]
            project_name = _project_name_from_cwd(folder_path)

    if not folder_path and sessions:
        folder_path = project_dir.as_posix()

    return project_name, folder_path, sessions


def scan_projects_root(projects_root: Path) -> List[Dict[str, Any]]:
    """
    Discover projects and sessions under a Claude ``projects/`` directory.

    Groups sessions by resolved ``cwd`` when multiple encoded dirs map to the
    same workspace.
    """
    by_cwd: Dict[str, Dict[str, Any]] = {}

    if not projects_root.is_dir():
        return []

    for entry in sorted(projects_root.iterdir()):
        if not entry.is_dir():
            continue
        project_name, folder_path, sessions = scan_project_dir(entry)
        if not sessions:
            continue

        key = folder_path or entry.as_posix()
        if key not in by_cwd:
            by_cwd[key] = {
                "project_name": project_name,
                "folder_path": folder_path,
                "encoded_dir": entry.name,
                "project_dir": entry,
                "sessions": [],
                "latest_session": None,
            }
        by_cwd[key]["sessions"].extend(sessions)

    projects = list(by_cwd.values())
    for project in projects:
        sessions = project["sessions"]
        if sessions:
            project["latest_session"] = max(
                sessions,
                key=lambda item: item.get("lastUpdatedAt", 0),
            )
        project["composers"] = project["sessions"]
        project["latest_dialog"] = project["latest_session"]

    projects.sort(
        key=lambda item: (
            item["latest_session"].get("lastUpdatedAt", 0)
            if item.get("latest_session")
            else 0
        ),
        reverse=True,
    )
    return projects


def scan_flat_sessions_root(sessions_root: Path) -> List[Dict[str, Any]]:
    """
    Scan a flat directory of session JSONL files (used by test fixtures).

    Layout: ``<root>/<session-id>.jsonl`` and ``<root>/<session-id>/subagents/``.
    """
    sessions: List[Dict[str, Any]] = []
    folder_path = ""

    for session_path in sorted(sessions_root.glob("*.jsonl")):
        if not session_path.is_file():
            continue
        meta = read_session_metadata(session_path)
        sessions.append(meta)
        if meta.get("cwd") and not folder_path:
            folder_path = meta["cwd"]

    if not sessions:
        return []

    project_name = _project_name_from_cwd(folder_path) if folder_path else sessions_root.name
    latest = max(sessions, key=lambda item: item.get("lastUpdatedAt", 0))
    return [
        {
            "project_name": project_name,
            "folder_path": folder_path or sessions_root.as_posix(),
            "encoded_dir": sessions_root.name,
            "project_dir": sessions_root,
            "sessions": sessions,
            "composers": sessions,
            "latest_session": latest,
            "latest_dialog": latest,
        }
    ]
