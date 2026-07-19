# Portions derived from cursor-chronicle (main) — licensed under AGPL-3.0-or-later
"""
Core CursorChatViewer class - project and dialog data access.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

from .db import readonly_connection
from .messages import get_dialog_messages
from .utils import (
    get_cursor_paths,
    load_global_composer_headers,
    parse_composer_workspace_identifier,
    parse_workspace_storage_meta,
)


def find_project(projects: List[Dict], name: str) -> Optional[Dict]:
    """Return the first project whose name contains ``name`` (case-insensitive)."""
    for project in projects:
        if name.lower() in project["project_name"].lower():
            return project
    return None


def find_composer(composers: List[Dict], name: str) -> Optional[Dict]:
    """Return the first composer whose name contains ``name`` (case-insensitive)."""
    for composer in composers:
        if name.lower() in composer.get("name", "").lower():
            return composer
    return None


class CursorChatViewer:
    """Access Cursor IDE chat history for context-tree review."""

    def __init__(self):
        paths = get_cursor_paths()
        self.cursor_config_path = paths[0]
        self.workspace_storage_path = paths[1]
        self.global_storage_path = paths[2]

    def get_dialog_messages(self, composer_id: str) -> List[Dict]:
        """Get all dialog messages by composer ID."""
        return get_dialog_messages(composer_id, db_path=self.global_storage_path)

    def get_projects(self) -> List[Dict]:
        """Get list of all projects with their metadata."""
        by_project: Dict[str, Dict] = {}
        seen_composer_ids: set = set()

        global_composers = load_global_composer_headers(self.global_storage_path)
        if global_composers:
            for comp in global_composers:
                composer_id = comp.get("composerId")
                if composer_id:
                    seen_composer_ids.add(composer_id)
                project_name, folder_path = parse_composer_workspace_identifier(comp)
                key = folder_path
                if key not in by_project:
                    ws = comp.get("workspaceIdentifier") or {}
                    by_project[key] = {
                        "workspace_id": ws.get("id", ""),
                        "project_name": project_name,
                        "folder_path": folder_path,
                        "composers": [],
                        "latest_dialog": None,
                        "state_db_path": str(self.global_storage_path),
                    }
                by_project[key]["composers"].append(comp)

        if self.workspace_storage_path.exists():
            for workspace_dir in self.workspace_storage_path.iterdir():
                if not workspace_dir.is_dir():
                    continue

                workspace_json = workspace_dir / "workspace.json"
                state_db = workspace_dir / "state.vscdb"

                if not workspace_json.exists() or not state_db.exists():
                    continue

                try:
                    with open(workspace_json, "r") as f:
                        workspace_data = json.load(f)

                    project_name, folder_path = parse_workspace_storage_meta(
                        workspace_data
                    )

                    with readonly_connection(state_db) as conn:
                        if conn is None:
                            continue
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT value FROM ItemTable WHERE key = 'composer.composerData'"
                        )
                        result = cursor.fetchone()

                        if result:
                            composer_data = json.loads(result[0])
                            composers = composer_data.get("allComposers", [])
                            new_composers = []
                            for c in composers:
                                cid = c.get("composerId")
                                if not cid or cid not in seen_composer_ids:
                                    if cid:
                                        seen_composer_ids.add(cid)
                                    new_composers.append(c)

                            if new_composers:
                                key = folder_path
                                if key not in by_project:
                                    by_project[key] = {
                                        "workspace_id": workspace_dir.name,
                                        "project_name": project_name,
                                        "folder_path": folder_path,
                                        "composers": [],
                                        "latest_dialog": None,
                                        "state_db_path": str(state_db),
                                    }
                                by_project[key]["composers"].extend(new_composers)

                except (OSError, json.JSONDecodeError, sqlite3.Error, KeyError):
                    continue

        projects = list(by_project.values())
        for info in projects:
            if info["composers"]:
                info["latest_dialog"] = max(
                    info["composers"],
                    key=lambda x: x.get("lastUpdatedAt", 0),
                )

        projects.sort(
            key=lambda x: (
                x["latest_dialog"].get("lastUpdatedAt", 0) if x["latest_dialog"] else 0
            ),
            reverse=True,
        )
        return projects

    def get_all_dialogs(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        project_filter: Optional[str] = None,
        dialog_filter: Optional[str] = None,
        sort_by: str = "date",
        sort_desc: bool = False,
        use_updated: bool = False,
    ) -> List[Dict]:
        """Get all dialogs across all projects, optionally filtered."""
        projects = self.get_projects()
        all_dialogs = []

        start_ts = int(start_date.timestamp() * 1000) if start_date else None
        end_ts = int(end_date.timestamp() * 1000) if end_date else None

        for project in projects:
            if project_filter:
                if project_filter.lower() not in project["project_name"].lower():
                    continue

            for composer in project.get("composers", []):
                if dialog_filter:
                    dialog_name = composer.get("name", "")
                    if dialog_filter.lower() not in dialog_name.lower():
                        continue

                last_updated = composer.get("lastUpdatedAt", 0)
                created_at = composer.get("createdAt", 0)
                filter_date = last_updated if use_updated else created_at

                if start_ts and filter_date < start_ts:
                    continue
                if end_ts and filter_date > end_ts:
                    continue

                all_dialogs.append(
                    {
                        "composer_id": composer.get("composerId", "unknown"),
                        "name": composer.get("name", "Untitled"),
                        "project_name": project["project_name"],
                        "folder_path": project["folder_path"],
                        "last_updated": last_updated,
                        "created_at": created_at,
                    }
                )

        if sort_by == "name":
            all_dialogs.sort(key=lambda x: x.get("name", "").lower(), reverse=sort_desc)
        elif sort_by == "project":
            all_dialogs.sort(
                key=lambda x: (
                    x.get("project_name", "").lower(),
                    x.get("name", "").lower(),
                ),
                reverse=sort_desc,
            )
        else:
            date_field = "last_updated" if use_updated else "created_at"
            all_dialogs.sort(key=lambda x: x.get(date_field, 0), reverse=sort_desc)

        return all_dialogs
