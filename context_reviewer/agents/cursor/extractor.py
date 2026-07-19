"""
Cursor-specific context extraction from tool calls.

Read-line-range math lives in ``_read_extraction``, edit-diff/patch math lives
in ``_edit_extraction``; this module owns generic tool-name dispatch, search
extraction, path resolution, and aggregation across a whole dialog.
"""

from __future__ import annotations

import os
from typing import Dict, List, Literal, Optional, Tuple

from context_reviewer.context.models import FileContextUsage

from context_reviewer.agents.cursor.content_lookup import ContentLookup
from context_reviewer.agents.cursor.paths import strip_file_uri
from context_reviewer.agents.cursor.tool_results import (
    CODE_SEARCH_TOOL_NAMES,
    SEARCH_TOOL_NAMES,
    extract_code_search_matches,
    extract_search_matches,
)

from ._edit_extraction import (  # noqa: F401 - re-exported for tests/consumers
    EDIT_TOOL_NAMES,
    _extract_lines_from_content_diff,
    extract_edit_context,
    is_edit_tool,
)
from ._read_extraction import (  # noqa: F401 - re-exported for tests/consumers
    READ_CONTEXT_TOOL_NAMES,
    extract_read_context,
)
from ._shared import _PATH_KEYS, _first_present, _parse_tool_args

ContextReadKind = Literal["read", "search", "code_search"]

CONTEXT_TOOL_NAMES = (
    READ_CONTEXT_TOOL_NAMES | SEARCH_TOOL_NAMES | CODE_SEARCH_TOOL_NAMES
)


def is_context_tool(tool_name: Optional[str]) -> bool:
    return tool_name in CONTEXT_TOOL_NAMES


def _normalize_path(path: str, project_root: Optional[str] = None) -> str:
    if not path:
        return ""

    normalized = path.replace("\\", "/")
    if normalized.startswith("file://"):
        normalized = strip_file_uri(normalized)

    if project_root:
        root = os.path.normpath(project_root)
        candidate = os.path.normpath(normalized)
        try:
            rel = os.path.relpath(candidate, root)
        except ValueError:
            rel = normalized
        if not rel.startswith(".."):
            return rel.replace("\\", "/")

    return normalized.replace("\\", "/")


def _resolve_project_relative_path(
    file_path: str, project_root: Optional[str]
) -> Optional[str]:
    """Normalize ``file_path`` relative to ``project_root``, or None if it falls outside it."""
    rel_path = _normalize_path(file_path, project_root)
    if not rel_path:
        return None

    if project_root and os.path.isabs(file_path.replace("\\", "/")):
        abs_path = os.path.normpath(file_path.replace("\\", "/"))
        root = os.path.normpath(project_root)
        try:
            if os.path.commonpath([abs_path, root]) != root:
                return None
        except ValueError:
            return None

    return rel_path


def _track_last_index(current: Optional[int], new: int) -> int:
    return new if current is None else max(current, new)


def _resolve_search_file(match_file: str, tool_args: Dict) -> str:
    search_path = _first_present(tool_args, _PATH_KEYS)
    if isinstance(search_path, str) and search_path:
        if match_file and os.path.basename(search_path) == match_file:
            return search_path
        if not match_file:
            return search_path
    return match_file or str(search_path or "")


def extract_search_context(
    tool_data: Dict,
) -> List[Tuple[str, FileContextUsage]]:
    tool_name = tool_data.get("name")
    if tool_name in CODE_SEARCH_TOOL_NAMES:
        matches = extract_code_search_matches(tool_data)
    elif tool_name in SEARCH_TOOL_NAMES:
        matches = extract_search_matches(tool_data)
    else:
        return []

    args = _parse_tool_args(tool_data)
    by_file: Dict[str, FileContextUsage] = {}
    for match in matches:
        file_path = _resolve_search_file(match.file, args)
        if not file_path:
            continue
        usage = by_file.setdefault(file_path, FileContextUsage())
        usage.lines.add(match.line_number)
    return list(by_file.items())


def _merge_edit_usage(
    target: Dict[str, FileContextUsage],
    file_path: str,
    usage: FileContextUsage,
    project_root: Optional[str],
    bubble_index: int,
) -> None:
    rel_path = _resolve_project_relative_path(file_path, project_root)
    if rel_path is None:
        return

    existing = target.setdefault(rel_path, FileContextUsage())
    existing.edit_hits += 1
    existing.last_edit_bubble_index = _track_last_index(
        existing.last_edit_bubble_index, bubble_index
    )
    if usage.deleted:
        existing.deleted = True
    if usage.edit_full_file:
        existing.edit_full_file = True
        existing.edit_lines.clear()
    elif not existing.edit_full_file:
        existing.edit_lines.update(usage.edit_lines)


def _clear_line_sets(usage: FileContextUsage) -> None:
    usage.lines.clear()
    usage.read_lines.clear()
    usage.search_lines.clear()
    usage.code_search_lines.clear()


def _merge_usage(
    target: Dict[str, FileContextUsage],
    file_path: str,
    usage: FileContextUsage,
    project_root: Optional[str],
    bubble_index: int,
    *,
    read_kind: ContextReadKind,
) -> None:
    rel_path = _resolve_project_relative_path(file_path, project_root)
    if rel_path is None:
        return

    existing = target.setdefault(rel_path, FileContextUsage())
    existing.hits += 1
    if read_kind == "read":
        existing.read_hits += 1
    elif read_kind == "search":
        existing.search_hits += 1
    else:
        existing.code_search_hits += 1
    existing.last_bubble_index = _track_last_index(
        existing.last_bubble_index, bubble_index
    )
    if usage.full_file:
        existing.full_file = True
        _clear_line_sets(existing)
    elif not existing.full_file:
        existing.lines.update(usage.lines)
        if read_kind == "read":
            existing.read_lines.update(usage.lines)
        elif read_kind == "search":
            existing.search_lines.update(usage.lines)
        else:
            existing.code_search_lines.update(usage.lines)


def collect_context_usage(
    messages: List[Dict],
    project_root: Optional[str] = None,
    *,
    min_bubble_index: Optional[int] = None,
    content_lookup: Optional[ContentLookup] = None,
) -> Dict[str, FileContextUsage]:
    usage_by_file: Dict[str, FileContextUsage] = {}

    for bubble_index, message in enumerate(messages):
        if min_bubble_index is not None and bubble_index <= min_bubble_index:
            continue

        tool_data = message.get("tool_data")
        if not tool_data:
            continue

        tool_name = tool_data.get("name")
        status = str(tool_data.get("status", "")).lower()
        if status and status not in {"completed", "success"}:
            continue

        if is_edit_tool(tool_name):
            edit_usage = extract_edit_context(
                tool_data,
                content_lookup=content_lookup,
            )
            if edit_usage:
                file_path, usage = edit_usage
                _merge_edit_usage(
                    usage_by_file,
                    file_path,
                    usage,
                    project_root,
                    bubble_index,
                )
            continue

        if not is_context_tool(tool_name):
            continue

        if tool_name in READ_CONTEXT_TOOL_NAMES:
            read_usage = extract_read_context(tool_data)
            if read_usage:
                file_path, usage = read_usage
                _merge_usage(
                    usage_by_file,
                    file_path,
                    usage,
                    project_root,
                    bubble_index,
                    read_kind="read",
                )
            continue

        if tool_name in CODE_SEARCH_TOOL_NAMES:
            read_kind: ContextReadKind = "code_search"
        else:
            read_kind = "search"
        for file_path, usage in extract_search_context(tool_data):
            _merge_usage(
                usage_by_file,
                file_path,
                usage,
                project_root,
                bubble_index,
                read_kind=read_kind,
            )

    return usage_by_file
