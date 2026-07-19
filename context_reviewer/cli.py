"""
Command-line interface for context-reviewer.
"""

import argparse
import os
import signal
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol

from context_reviewer.agents.claude.context import build_context_tree as build_claude_context_tree
from context_reviewer.agents.claude.presentation import (
    print_dialogs as print_claude_dialogs,
)
from context_reviewer.agents.claude.presentation import (
    print_projects as print_claude_projects,
)
from context_reviewer.agents.claude.viewer import (
    ClaudeSessionViewer,
    find_project as find_claude_project,
)
from context_reviewer.agents.claude.viewer import find_session
from context_reviewer.agents.cursor.content_lookup import CursorContentLookup
from context_reviewer.agents.cursor.context import build_context_tree as build_cursor_context_tree
from context_reviewer.agents.cursor.presentation import (
    print_all_dialogs,
    print_dialogs as print_cursor_dialogs,
    print_projects as print_cursor_projects,
)
from context_reviewer.agents.cursor.viewer import (
    CursorChatViewer,
    find_composer,
    find_project as find_cursor_project,
)
from context_reviewer.render import format_context_tree


class ContextViewer(Protocol):
    def get_projects(self) -> List[Dict[str, Any]]: ...


def parse_date(date_str: str) -> datetime:
    """Parse date string in various formats."""
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%d.%m.%Y",
        "%d/%m/%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        f"Invalid date format: {date_str}. Use YYYY-MM-DD or similar."
    )


def parse_positive_int(value: str) -> int:
    """Parse and validate a positive integer value."""
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(f"Invalid integer value: {value}") from exc

    if parsed <= 0:
        raise argparse.ArgumentTypeError("Value must be a positive integer")
    return parsed


def resolve_use_color(color: Optional[bool] = None) -> bool:
    """Return whether ANSI colors should be used for terminal output."""
    if color is not None:
        return color
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


def _select_project(
    projects: List[Dict[str, Any]],
    project_name: Optional[str],
    find_project_fn,
) -> Optional[Dict[str, Any]]:
    if not projects:
        print("No projects found.")
        return None

    if project_name:
        project = find_project_fn(projects, project_name)
        if not project:
            print(f"Project '{project_name}' not found.")
            return None
        return project

    return projects[0]


def show_cursor_context_tree(
    viewer: CursorChatViewer,
    project_name: Optional[str] = None,
    dialog_name: Optional[str] = None,
    *,
    mode: str = "reads",
    files_only: bool = False,
    context_tree_depth: Optional[int] = None,
    last_turn: bool = False,
    color: Optional[bool] = None,
) -> None:
    """Show context tree for a Cursor dialog."""
    projects = viewer.get_projects()
    project = _select_project(projects, project_name, find_cursor_project)
    if project is None:
        return

    composer = None
    if dialog_name:
        composer = find_composer(project["composers"], dialog_name)
        if not composer:
            print(
                f"Dialog '{dialog_name}' not found in project '{project['project_name']}'."
            )
            return
    elif project["composers"]:
        composer = max(project["composers"], key=lambda item: item.get("lastUpdatedAt", 0))
    else:
        print(f"No dialogs found in project '{project['project_name']}'.")
        return

    composer_id = composer.get("composerId")
    if not composer_id:
        print("Dialog ID not found.")
        return

    try:
        messages = viewer.get_dialog_messages(composer_id)
        if not messages:
            print("No messages found in dialog.")
            return

        content_lookup = CursorContentLookup(viewer.global_storage_path)
        tree = build_cursor_context_tree(
            messages,
            project_root=project.get("folder_path"),
            last_turn=last_turn,
            content_lookup=content_lookup,
        )
        print(
            format_context_tree(
                tree.usage,
                mode=mode,
                files_only=files_only,
                total_bubbles=tree.total_bubbles,
                recency_bubble_offset=tree.recency_bubble_offset,
                empty_message=tree.empty_message,
                color=resolve_use_color(color),
                max_depth=context_tree_depth,
            )
        )
    except Exception as exc:
        print(f"Error reading dialog: {exc}")


def show_claude_context_tree(
    viewer: ClaudeSessionViewer,
    project_name: Optional[str] = None,
    dialog_name: Optional[str] = None,
    *,
    mode: str = "reads",
    files_only: bool = False,
    context_tree_depth: Optional[int] = None,
    last_turn: bool = False,
    color: Optional[bool] = None,
) -> None:
    """Show context tree for a Claude Code session."""
    projects = viewer.get_projects()
    project = _select_project(projects, project_name, find_claude_project)
    if project is None:
        return

    session = None
    sessions = project.get("sessions", [])
    if dialog_name:
        session = find_session(sessions, dialog_name)
        if not session:
            print(
                f"Session '{dialog_name}' not found in project '{project['project_name']}'."
            )
            return
    elif sessions:
        session = max(sessions, key=lambda item: item.get("lastUpdatedAt", 0))
    else:
        print(f"No sessions found in project '{project['project_name']}'.")
        return

    session_id = session.get("session_id")
    if not session_id:
        print("Session ID not found.")
        return

    try:
        messages = viewer.get_session_messages(session_id)
        if not messages:
            print("No messages found in session.")
            return

        tree = build_claude_context_tree(
            messages,
            project_root=project.get("folder_path"),
            last_turn=last_turn,
        )
        print(
            format_context_tree(
                tree.usage,
                mode=mode,
                files_only=files_only,
                total_bubbles=tree.total_bubbles,
                recency_bubble_offset=tree.recency_bubble_offset,
                empty_message=tree.empty_message,
                color=resolve_use_color(color),
                max_depth=context_tree_depth,
            )
        )
    except Exception as exc:
        print(f"Error reading session: {exc}")


def show_context_tree(
    viewer: ContextViewer,
    project_name: Optional[str] = None,
    dialog_name: Optional[str] = None,
    *,
    agent: str,
    mode: str = "reads",
    files_only: bool = False,
    context_tree_depth: Optional[int] = None,
    last_turn: bool = False,
    color: Optional[bool] = None,
) -> None:
    """Dispatch context-tree rendering to the selected agent backend."""
    if agent == "claude":
        show_claude_context_tree(
            viewer,  # type: ignore[arg-type]
            project_name,
            dialog_name,
            mode=mode,
            files_only=files_only,
            context_tree_depth=context_tree_depth,
            last_turn=last_turn,
            color=color,
        )
        return

    show_cursor_context_tree(
        viewer,  # type: ignore[arg-type]
        project_name,
        dialog_name,
        mode=mode,
        files_only=files_only,
        context_tree_depth=context_tree_depth,
        last_turn=last_turn,
        color=color,
    )


def create_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        description="Context Reviewer - Review context used by AI coding agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --cursor --list-projects              # List Cursor projects
  %(prog)s --claude --list-projects              # List Claude Code projects
  %(prog)s --cursor --list-dialogs myproject     # List Cursor dialogs
  %(prog)s --claude --list-dialogs myproject     # List Claude sessions
  %(prog)s --cursor --list-all                   # List all Cursor dialogs
  %(prog)s --cursor -p myproject -d "my chat"    # Cursor context tree
  %(prog)s --claude -p myproject -d "my chat"    # Claude context tree
  %(prog)s --claude -p myproject -d "my chat" --files-only
  %(prog)s --claude -p myproject -d "my chat" --last-turn --context-tree-depth 2
        """,
    )

    agent_group = parser.add_mutually_exclusive_group(required=True)
    agent_group.add_argument(
        "--cursor",
        action="store_true",
        help="Use Cursor IDE as the agent data source",
    )
    agent_group.add_argument(
        "--claude",
        action="store_true",
        help="Use Claude Code as the agent data source",
    )

    parser.add_argument(
        "--project", "-p", help="Project name (partial match supported)"
    )
    parser.add_argument(
        "--dialog",
        "-d",
        help="Dialog/session name (partial match supported)",
    )
    parser.add_argument(
        "--list-projects", action="store_true", help="Show list of projects"
    )
    parser.add_argument(
        "--list-dialogs",
        help="Show list of dialogs/sessions for project",
    )
    parser.add_argument(
        "--list-all",
        action="store_true",
        help="List all dialogs (Cursor only for now)",
    )
    parser.add_argument(
        "--from", dest="start_date", type=parse_date, help="Filter after date"
    )
    parser.add_argument(
        "--before", "--to", dest="end_date", type=parse_date, help="Filter before date"
    )
    parser.add_argument(
        "--limit",
        type=parse_positive_int,
        default=50,
        help="Maximum dialogs (default: 50)",
    )
    parser.add_argument(
        "--sort", choices=["date", "name", "project"], default="date", help="Sort by"
    )
    parser.add_argument("--desc", action="store_true", help="Sort descending")
    parser.add_argument("--updated", action="store_true", help="Use last updated date")
    parser.add_argument(
        "--files-only",
        action="store_true",
        help="List files only (omit line ranges and checkmarks)",
    )
    parser.add_argument(
        "--edits",
        action="store_true",
        help="Show edits view instead of reads (edit counts and edited line ranges)",
    )
    parser.add_argument(
        "--context-tree-depth",
        type=parse_positive_int,
        default=None,
        help="Max directory depth below root (default: unlimited)",
    )
    parser.add_argument(
        "--last-turn",
        action="store_true",
        help="Show only files touched after the last user message",
    )
    color_group = parser.add_mutually_exclusive_group()
    color_group.add_argument(
        "--color",
        action="store_true",
        default=None,
        help="Force ANSI color output for context tree",
    )
    color_group.add_argument(
        "--no-color",
        action="store_false",
        dest="color",
        help="Disable ANSI color output for context tree",
    )

    return parser


def main() -> None:
    """Main entry point."""
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    parser = create_parser()
    args = parser.parse_args()
    agent = "claude" if args.claude else "cursor"

    if args.list_all and agent == "claude":
        print("Error: --list-all is not supported for --claude yet.")
        sys.exit(1)

    if agent == "claude":
        viewer: ContextViewer = ClaudeSessionViewer()
        if args.list_projects:
            print_claude_projects(viewer)  # type: ignore[arg-type]
        elif args.list_dialogs:
            print_claude_dialogs(viewer, args.list_dialogs)  # type: ignore[arg-type]
        else:
            show_context_tree(
                viewer,
                args.project,
                args.dialog,
                agent=agent,
                mode="edits" if args.edits else "reads",
                files_only=args.files_only,
                context_tree_depth=args.context_tree_depth,
                last_turn=args.last_turn,
                color=args.color,
            )
        return

    cursor_viewer = CursorChatViewer()
    if args.list_projects:
        print_cursor_projects(cursor_viewer)
    elif args.list_dialogs:
        print_cursor_dialogs(cursor_viewer, args.list_dialogs)
    elif args.list_all:
        print_all_dialogs(
            cursor_viewer,
            start_date=args.start_date,
            end_date=args.end_date,
            project_filter=args.project,
            limit=args.limit,
            sort_by=args.sort,
            sort_desc=args.desc,
            use_updated=args.updated,
        )
    else:
        show_context_tree(
            cursor_viewer,
            args.project,
            args.dialog,
            agent=agent,
            mode="edits" if args.edits else "reads",
            files_only=args.files_only,
            context_tree_depth=args.context_tree_depth,
            last_turn=args.last_turn,
            color=args.color,
        )


if __name__ == "__main__":
    main()
