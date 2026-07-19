"""
Command-line interface for context-reviewer.
"""

import argparse
import os
import sys
from datetime import datetime
from typing import Optional

from context_reviewer.agents.cursor.context import build_context_tree
from context_reviewer.agents.cursor.viewer import CursorChatViewer
from context_reviewer.render import format_context_tree


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


def show_context_tree(
    viewer: CursorChatViewer,
    project_name: Optional[str] = None,
    dialog_name: Optional[str] = None,
    files_only: bool = False,
    context_tree_depth: Optional[int] = None,
    last_turn: bool = False,
    color: Optional[bool] = None,
):
    """Show context tree for a dialog."""
    projects = viewer.get_projects()

    if not projects:
        print("No projects found.")
        return

    project = None
    if project_name:
        for p in projects:
            if project_name.lower() in p["project_name"].lower():
                project = p
                break
        if not project:
            print(f"Project '{project_name}' not found.")
            return
    else:
        project = projects[0]

    composer = None
    if dialog_name:
        for c in project["composers"]:
            c_name = c.get("name", "").lower()
            if dialog_name.lower() in c_name:
                composer = c
                break
        if not composer:
            print(
                f"Dialog '{dialog_name}' not found in project '{project['project_name']}'."
            )
            return
    else:
        if project["composers"]:
            composer = max(
                project["composers"], key=lambda x: x.get("lastUpdatedAt", 0)
            )
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

        tree = build_context_tree(
            messages,
            project_root=project.get("folder_path"),
            last_turn=last_turn,
        )
        print(
            format_context_tree(
                tree.usage,
                files_only=files_only,
                total_bubbles=tree.total_bubbles,
                recency_bubble_offset=tree.recency_bubble_offset,
                empty_message=tree.empty_message,
                color=resolve_use_color(color),
                max_depth=context_tree_depth,
            )
        )

    except Exception as e:
        print(f"Error reading dialog: {e}")


def create_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        description="Context Reviewer - Review context used by AI coding agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --cursor --list-projects              # List all projects
  %(prog)s --cursor --list-dialogs myproject     # List dialogs in project
  %(prog)s --cursor --list-all                   # List all dialogs (oldest first)
  %(prog)s --cursor --list-all --desc            # List all dialogs (newest first)
  %(prog)s --cursor -p myproject -d "my chat"    # Show context tree for dialog
  %(prog)s --cursor -p myproject -d "my chat" --files-only
  %(prog)s --cursor -p myproject -d "my chat" --last-turn --context-tree-depth 2
        """,
    )

    parser.add_argument(
        "--cursor",
        action="store_true",
        help="Use Cursor IDE as the agent data source (required for now)",
    )

    parser.add_argument(
        "--project", "-p", help="Project name (partial match supported)"
    )
    parser.add_argument("--dialog", "-d", help="Dialog name (partial match supported)")
    parser.add_argument(
        "--list-projects", action="store_true", help="Show list of projects"
    )
    parser.add_argument("--list-dialogs", help="Show list of dialogs for project")
    parser.add_argument("--list-all", action="store_true", help="List all dialogs")
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


def _require_cursor(args: argparse.Namespace) -> bool:
    if args.cursor:
        return True
    print("Error: --cursor is required (only Cursor is supported for now).")
    return False


def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not _require_cursor(args):
        sys.exit(1)

    viewer = CursorChatViewer()

    if args.list_projects:
        viewer.list_projects()
    elif args.list_dialogs:
        viewer.list_dialogs(args.list_dialogs)
    elif args.list_all:
        viewer.list_all_dialogs(
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
            viewer,
            args.project,
            args.dialog,
            files_only=args.files_only,
            context_tree_depth=args.context_tree_depth,
            last_turn=args.last_turn,
            color=args.color,
        )


if __name__ == "__main__":
    main()
