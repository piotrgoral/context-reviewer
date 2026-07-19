"""Claude Code session data access."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from .messages import load_session_messages
from .paths import get_projects_dir
from .utils import scan_flat_sessions_root, scan_projects_root


def find_project(projects: List[Dict], name: str) -> Optional[Dict]:
    """Return the first project whose name contains ``name`` (case-insensitive)."""
    for project in projects:
        if name.lower() in project["project_name"].lower():
            return project
    return None


def find_session(sessions: List[Dict], name: str) -> Optional[Dict]:
    """Return the first session matching title, slug, or id (case-insensitive)."""
    lowered = name.lower()
    for session in sessions:
        for key in ("name", "title", "slug", "session_id"):
            value = session.get(key)
            if isinstance(value, str) and lowered in value.lower():
                return session
    return None


class ClaudeSessionViewer:
    """Access Claude Code session history for context-tree review."""

    def __init__(
        self,
        *,
        projects_root: Optional[Path] = None,
        flat_layout: bool = False,
    ) -> None:
        """
        Args:
            projects_root: Override projects directory (for tests/fixtures).
            flat_layout: When True, treat ``projects_root`` as a flat session dir
                (``materials/`` layout) instead of ``projects/<encoded>/``.
        """
        self._projects_root = projects_root
        self._flat_layout = flat_layout

    @property
    def projects_root(self) -> Path:
        if self._projects_root is not None:
            return self._projects_root
        return get_projects_dir()

    def get_projects(self) -> List[Dict]:
        """List projects with session metadata."""
        root = self.projects_root
        if self._flat_layout or self._looks_flat(root):
            return scan_flat_sessions_root(root)
        return scan_projects_root(root)

    def _looks_flat(self, root: Path) -> bool:
        if not root.is_dir():
            return False
        if any(root.glob("*.jsonl")):
            return True
        return not any(child.is_dir() for child in root.iterdir())

    def get_dialog_messages(self, session_id: str) -> List[Dict]:
        """Load normalized messages for a session id (Cursor-compatible alias)."""
        return self.get_session_messages(session_id)

    def get_session_messages(self, session_id: str) -> List[Dict]:
        """Load normalized messages for a session, including subagents."""
        session = self._find_session_by_id(session_id)
        if session is None:
            return []
        session_path = Path(session["session_path"])
        return load_session_messages(session_path)

    def _find_session_by_id(self, session_id: str) -> Optional[Dict]:
        for project in self.get_projects():
            for session in project.get("sessions", []):
                if session.get("session_id") == session_id:
                    return session
        return None
