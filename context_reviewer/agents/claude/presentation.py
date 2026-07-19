"""CLI presentation for Claude Code project/session listings."""

from __future__ import annotations

from datetime import datetime

from .viewer import ClaudeSessionViewer, find_project, find_session


def print_projects(viewer: ClaudeSessionViewer) -> None:
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
        print(f"   Sessions: {len(project.get('sessions', []))}")

        latest = project.get("latest_session")
        if latest:
            name = latest.get("name", "Untitled")
            timestamp = latest.get("lastUpdatedAt", 0)
            if timestamp:
                date = datetime.fromtimestamp(timestamp / 1000)
                print(f"   Latest: {name} ({date.strftime('%Y-%m-%d %H:%M')})")
        print()


def print_dialogs(viewer: ClaudeSessionViewer, project_name: str) -> None:
    """Print list of sessions for a project."""
    projects = viewer.get_projects()
    project = find_project(projects, project_name)

    if not project:
        print(f"Project '{project_name}' not found.")
        return

    sessions = project.get("sessions", [])
    if not sessions:
        print(f"No sessions found in project '{project['project_name']}'.")
        return

    print(f"Sessions in project '{project['project_name']}':")
    print("=" * 50)

    sessions.sort(key=lambda item: item.get("lastUpdatedAt", 0), reverse=True)

    for session in sessions:
        name = session.get("name", "Untitled")
        session_id = session.get("session_id", "unknown")
        timestamp = session.get("lastUpdatedAt", 0)
        branch = session.get("git_branch")

        if timestamp:
            date = datetime.fromtimestamp(timestamp / 1000)
            print(f"💬 {name}")
            print(f"   ID: {session_id}")
            print(f"   Updated: {date.strftime('%Y-%m-%d %H:%M')}")
        else:
            print(f"💬 {name} (ID: {session_id})")
        if branch:
            print(f"   Branch: {branch}")
        print()
