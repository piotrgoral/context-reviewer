# Portions derived from cursor-chronicle (main) — licensed under AGPL-3.0-or-later
"""
Shared utilities and constants for Cursor Chronicle.
"""

import json
import os
import signal
import sqlite3
import sys
import urllib.parse
from pathlib import Path
from typing import Dict, List, Tuple

# Handle broken pipe gracefully (SIGPIPE is Unix-only)
if hasattr(signal, "SIGPIPE"):
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

_CODE_WORKSPACE_SUFFIX = ".code-workspace"


def format_workspace_project_display_name(basename: str) -> str:
    """
    Human-friendly project label from a workspace path basename.

    Does not change filesystem paths; used only for ``project_name`` in listings
    and filters.
    """
    if basename == "workspace.json":
        return "Unnamed Workspace"
    if basename.endswith(_CODE_WORKSPACE_SUFFIX):
        stem = basename[: -len(_CODE_WORKSPACE_SUFFIX)]
        return stem if stem else "Unnamed Workspace"
    return basename


def parse_workspace_storage_meta(workspace_data: Dict) -> Tuple[str, str]:
    """
    Parse workspace.json from Cursor/VS Code workspace storage.

    Single-folder workspaces set ``folder``; multi-root workspaces set ``workspace``
    to the URI of the ``.code-workspace`` file.

    Returns:
        (project_name, folder_path) for display. For ``file://`` URIs, ``folder_path``
        is the decoded filesystem path and ``project_name`` is its basename.
    """
    folder_uri = workspace_data.get("folder") or ""
    workspace_value = workspace_data.get("workspace")
    workspace_uri = ""
    if isinstance(workspace_value, str) and workspace_value:
        workspace_uri = workspace_value
    elif isinstance(workspace_value, dict):
        nested = workspace_value.get("configPath") or workspace_value.get("folder")
        if isinstance(nested, str):
            workspace_uri = nested

    effective_uri = folder_uri or workspace_uri

    if effective_uri.startswith("file://"):
        folder_path = urllib.parse.unquote(effective_uri[7:])
        raw_basename = os.path.basename(folder_path)
        return format_workspace_project_display_name(raw_basename), folder_path

    return (effective_uri, effective_uri)


# Absolute path to Cursor's per-user "User" directory (contains workspaceStorage, etc.).
# When set (non-empty after stripping), overrides OS-specific defaults below.
CURSOR_USER_DIR_ENV = "CONTEXT_REVIEWER_CURSOR_USER_DIR"
LEGACY_CURSOR_USER_DIR_ENV = "CURSOR_CHRONICLE_CURSOR_USER_DIR"


def _cursor_user_dir() -> Path:
    """
    Directory where Cursor stores per-user data (workspaceStorage, globalStorage, etc.).

    Override with the environment variable CURSOR_CHRONICLE_CURSOR_USER_DIR (tilde expands).

    Otherwise matches VS Code-style layout: macOS and Windows use app support / roaming;
    Linux and other Unixes use XDG-style ~/.config.
    """
    for env_name in (CURSOR_USER_DIR_ENV, LEGACY_CURSOR_USER_DIR_ENV):
        override = os.environ.get(env_name)
        if override is not None and override.strip():
            return Path(override.strip()).expanduser()

    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Cursor" / "User"
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "Cursor" / "User"
        return home / "AppData" / "Roaming" / "Cursor" / "User"
    return home / ".config" / "Cursor" / "User"


def get_cursor_paths() -> tuple:
    """
    Get standard Cursor IDE paths for the current OS.

    If CURSOR_CHRONICLE_CURSOR_USER_DIR is set, it is used as the Cursor User directory.

    Returns:
        Tuple of (cursor_config_path, workspace_storage_path, global_storage_path)
    """
    cursor_config_path = _cursor_user_dir()
    workspace_storage_path = cursor_config_path / "workspaceStorage"
    global_storage_path = cursor_config_path / "globalStorage" / "state.vscdb"
    return cursor_config_path, workspace_storage_path, global_storage_path


def parse_composer_workspace_identifier(comp: Dict) -> Tuple[str, str]:
    """
    Extract (project_name, folder_path) from a Cursor 3.0+ composer header's
    ``workspaceIdentifier`` field.
    """
    ws = comp.get("workspaceIdentifier") or {}
    uri_obj = ws.get("uri") or {}
    if isinstance(uri_obj, dict):
        folder_path = (
            uri_obj.get("fsPath") or uri_obj.get("path") or uri_obj.get("external") or ""
        )
    elif isinstance(uri_obj, str):
        folder_path = uri_obj
    else:
        folder_path = ""

    if isinstance(folder_path, str) and folder_path.startswith("file://"):
        folder_path = urllib.parse.unquote(folder_path[7:])
    if not folder_path:
        folder_path = "unknown"
    project_name = os.path.basename(folder_path) or folder_path
    return project_name, folder_path



def load_global_composer_headers(global_storage_path: Path) -> List[Dict]:
    """Load composer headers from global ``state.vscdb``."""
    if not global_storage_path.exists():
        return []
    try:
        with sqlite3.connect(global_storage_path) as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT composerId, createdAt, lastUpdatedAt, value "
                    "FROM composerHeaders"
                )
                headers: List[Dict] = []
                for composer_id, created_at, last_updated_at, value in cur.fetchall():
                    try:
                        if not value:
                            continue
                        comp = json.loads(value)
                        if not isinstance(comp, dict):
                            continue
                        if not comp.get("composerId"):
                            comp["composerId"] = composer_id
                        comp["createdAt"] = comp.get("createdAt") or created_at or 0
                        comp["lastUpdatedAt"] = (
                            comp.get("lastUpdatedAt") or last_updated_at or 0
                        )
                        headers.append(comp)
                    except (
                        json.JSONDecodeError,
                        TypeError,
                        AttributeError,
                        UnicodeDecodeError,
                    ):
                        continue
                if headers:
                    return headers
            except sqlite3.OperationalError:
                pass

            cur.execute(
                "SELECT value FROM ItemTable WHERE key = 'composer.composerHeaders'"
            )
            row = cur.fetchone()
            if row:
                return json.loads(row[0]).get("allComposers", [])
    except Exception:
        pass
    return []


# Tool type mapping for display
TOOL_TYPES = {
    1: "🔍 Codebase Search",
    3: "🔎 Grep Search",
    5: "📖 Read File",
    6: "📁 List Directory",
    7: "✏️ Edit File",
    8: "🔍 File Search",
    9: "🔍 Codebase Search",
    11: "🗑️ Delete File",
    12: "🔄 Reapply",
    15: "⚡ Terminal Command",
    16: "📋 Fetch Rules",
    18: "🌐 Web Search",
    19: "🔧 MCP Tool",
}
