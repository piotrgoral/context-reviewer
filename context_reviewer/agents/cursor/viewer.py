# Portions derived from cursor-chronicle (main) — licensed under AGPL-3.0-or-later
"""
Core CursorChatViewer class - project and dialog data access.
"""

import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

from .messages import get_dialog_messages
from .utils import (
    get_cursor_paths,
    load_global_composer_headers,
    parse_composer_workspace_identifier,
    parse_workspace_storage_meta,
)


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

                    with sqlite3.connect(state_db) as conn:
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

                except Exception:
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

    def list_projects(self):
        """Show list of all projects."""
        projects = self.get_projects()

        if not projects:
            print("No projects found.")
            return

        print("Available projects:")
        print("=" * 50)

        for project in projects:
            print(f"📁 {project['project_name']}")
            print(f"   Path: {project['folder_path']}")
            print(f"   Dialogs: {len(project['composers'])}")

            if project["latest_dialog"]:
                latest = project["latest_dialog"]
                name = latest.get("name", "Untitled")
                timestamp = latest.get("lastUpdatedAt", 0)
                if timestamp:
                    date = datetime.fromtimestamp(timestamp / 1000)
                    print(f"   Latest: {name} ({date.strftime('%Y-%m-%d %H:%M')})")
            print()

    def list_dialogs(self, project_name: str):
        """Show list of dialogs for project."""
        projects = self.get_projects()

        project = None
        for p in projects:
            if project_name.lower() in p["project_name"].lower():
                project = p
                break

        if not project:
            print(f"Project '{project_name}' not found.")
            return

        composers = project["composers"]
        if not composers:
            print(f"No dialogs found in project '{project['project_name']}'.")
            return

        print(f"Dialogs in project '{project['project_name']}':")
        print("=" * 50)

        composers.sort(key=lambda x: x.get("lastUpdatedAt", 0), reverse=True)

        for composer in composers:
            name = composer.get("name", "Untitled")
            composer_id = composer.get("composerId", "unknown")
            timestamp = composer.get("lastUpdatedAt", 0)

            if timestamp:
                date = datetime.fromtimestamp(timestamp / 1000)
                print(f"💬 {name}")
                print(f"   ID: {composer_id}")
                print(f"   Updated: {date.strftime('%Y-%m-%d %H:%M')}")
            else:
                print(f"💬 {name} (ID: {composer_id})")
            print()

    def list_all_dialogs(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        project_filter: Optional[str] = None,
        limit: int = 50,
        sort_by: str = "date",
        sort_desc: bool = False,
        use_updated: bool = False,
    ):
        """Display all dialogs across all projects."""
        dialogs = self.get_all_dialogs(
            start_date, end_date, project_filter, sort_by, sort_desc, use_updated
        )

        if not dialogs:
            date_info = ""
            if start_date or end_date:
                if start_date and end_date:
                    date_info = f" between {start_date.strftime('%Y-%m-%d')} and {end_date.strftime('%Y-%m-%d')}"
                elif start_date:
                    date_info = f" after {start_date.strftime('%Y-%m-%d')}"
                else:
                    date_info = f" before {end_date.strftime('%Y-%m-%d')}"
            print(f"No dialogs found{date_info}.")
            return

        header_parts = ["All dialogs"]
        if project_filter:
            header_parts.append(f"in '{project_filter}'")
        if start_date or end_date:
            if start_date and end_date:
                header_parts.append(
                    f"from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
                )
            elif start_date:
                header_parts.append(f"after {start_date.strftime('%Y-%m-%d')}")
            else:
                header_parts.append(f"before {end_date.strftime('%Y-%m-%d')}")

        print(" ".join(header_parts) + ":")
        print(f"Found {len(dialogs)} dialog(s)")
        print("=" * 60)

        displayed = 0
        for dialog in dialogs:
            if displayed >= limit:
                remaining = len(dialogs) - limit
                print(f"... and {remaining} more dialogs (use --limit to see more)")
                break

            name = dialog["name"]
            composer_id = dialog["composer_id"]
            project_name = dialog["project_name"]
            timestamp = dialog["last_updated"]
            created_at = dialog["created_at"]

            print(f"💬 {name}")
            print(f"   📁 Project: {project_name}")
            print(f"   🔗 ID: {composer_id}")

            if timestamp:
                date = datetime.fromtimestamp(timestamp / 1000)
                print(f"   📅 Updated: {date.strftime('%Y-%m-%d %H:%M')}")
            if created_at:
                date = datetime.fromtimestamp(created_at / 1000)
                print(f"   📅 Created: {date.strftime('%Y-%m-%d %H:%M')}")
            print()
            displayed += 1
