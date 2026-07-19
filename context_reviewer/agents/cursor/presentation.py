# Portions derived from cursor-chronicle (main) — licensed under AGPL-3.0-or-later
"""
CLI presentation (print-based listings) for Cursor project/dialog data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from .viewer import CursorChatViewer


def print_projects(viewer: CursorChatViewer) -> None:
    """Print list of all projects."""
    projects = viewer.get_projects()

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


def print_dialogs(viewer: CursorChatViewer, project_name: str) -> None:
    """Print list of dialogs for a project."""
    projects = viewer.get_projects()

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


def print_all_dialogs(
    viewer: CursorChatViewer,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    project_filter: Optional[str] = None,
    dialog_filter: Optional[str] = None,
    limit: int = 50,
    sort_by: str = "date",
    sort_desc: bool = False,
    use_updated: bool = False,
) -> None:
    """Print all dialogs across all projects, optionally filtered."""
    dialogs = viewer.get_all_dialogs(
        start_date=start_date,
        end_date=end_date,
        project_filter=project_filter,
        dialog_filter=dialog_filter,
        sort_by=sort_by,
        sort_desc=sort_desc,
        use_updated=use_updated,
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
