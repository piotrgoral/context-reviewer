"""
Cursor-specific context extraction from tool calls.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

from context_reviewer.context.models import FileContextUsage

from context_reviewer.agents.cursor.tool_results import (
    CODE_SEARCH_TOOL_NAMES,
    SEARCH_TOOL_NAMES,
    extract_code_search_matches,
    extract_search_matches,
)

READ_CONTEXT_TOOL_NAMES = frozenset({"read_file", "read_file_v2"})
EDIT_TOOL_NAMES = frozenset(
    {
        "edit_file_v2",
        "search_replace",
        "write",
        "edit_file",
        "edit_notebook",
        "apply_patch",
        "MultiEdit",
        "delete_file",
    }
)
CONTEXT_TOOL_NAMES = (
    READ_CONTEXT_TOOL_NAMES | SEARCH_TOOL_NAMES | CODE_SEARCH_TOOL_NAMES
)

_PATH_KEYS = (
    "path",
    "targetFile",
    "target_file",
    "file_path",
    "relativeWorkspacePath",
    "relative_workspace_path",
    "effectiveUri",
    "target_notebook",
)
_START_KEYS = ("offset", "start_line_one_indexed", "startLineOneIndexed")
_END_KEYS = (
    "end_line_one_indexed",
    "end_line_one_indexed_inclusive",
    "endLineOneIndexedInclusive",
)
_RESULT_START_KEYS = ("startLineOneIndexed",)
_RESULT_END_KEYS = ("endLineOneIndexedInclusive",)
_LIMIT_KEYS = ("limit", "maxLines")
_FULL_FILE_KEYS = (
    "readEntireFile",
    "should_read_entire_file",
    "readFullFile",
)
def is_context_tool(tool_name: Optional[str]) -> bool:
    return tool_name in CONTEXT_TOOL_NAMES


def is_edit_tool(tool_name: Optional[str]) -> bool:
    return tool_name in EDIT_TOOL_NAMES


def _parse_json_field(value: Any) -> Optional[Any]:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return None


def _parse_tool_args(tool_data: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for key in ("params", "rawArgs"):
        parsed = _parse_json_field(tool_data.get(key))
        if isinstance(parsed, dict):
            merged.update(parsed)
    return merged


def _parse_tool_result(tool_data: Dict[str, Any]) -> Dict[str, Any]:
    parsed = _parse_json_field(tool_data.get("result"))
    return parsed if isinstance(parsed, dict) else {}


def _first_present(data: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"true", "1", "yes"}
    return bool(value)


def _line_count_from_contents(contents: Any) -> int:
    if not isinstance(contents, str) or not contents:
        return 0
    return len(contents.splitlines())


def _has_explicit_read_range(args: Dict[str, Any]) -> bool:
    return (
        _first_present(args, _START_KEYS) is not None
        or _first_present(args, _END_KEYS) is not None
        or _first_present(args, _LIMIT_KEYS) is not None
    )


def _is_metadata_only_full_read(
    args: Dict[str, Any],
    result: Dict[str, Any],
    total_lines: Optional[int],
    content_lines: int,
) -> bool:
    if total_lines is None or total_lines <= 0:
        return False
    if content_lines > 0:
        return False
    if _has_explicit_read_range(args):
        return False
    if _first_present(result, _RESULT_START_KEYS) is not None:
        return False
    if _first_present(result, _RESULT_END_KEYS) is not None:
        return False
    if result.get("contents") not in (None, ""):
        return False
    return True


def _normalize_path(path: str, project_root: Optional[str] = None) -> str:
    if not path:
        return ""

    normalized = path.replace("\\", "/")
    if normalized.startswith("file://"):
        from urllib.parse import unquote, urlparse

        normalized = unquote(urlparse(normalized).path)

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


def _resolve_search_file(match_file: str, tool_args: Dict[str, Any]) -> str:
    search_path = _first_present(tool_args, _PATH_KEYS)
    if isinstance(search_path, str) and search_path:
        if match_file and os.path.basename(search_path) == match_file:
            return search_path
        if not match_file:
            return search_path
    return match_file or str(search_path or "")

def extract_read_context(
    tool_data: Dict[str, Any],
) -> Optional[Tuple[str, FileContextUsage]]:
    tool_name = tool_data.get("name")
    if tool_name not in READ_CONTEXT_TOOL_NAMES:
        return None

    args = _parse_tool_args(tool_data)
    result = _parse_tool_result(tool_data)

    file_path = _first_present(args, _PATH_KEYS) or _first_present(result, _PATH_KEYS)
    if not isinstance(file_path, str) or not file_path:
        return None

    total_lines = _first_present(result, ("totalLinesInFile", "totalLines"))
    if total_lines is not None:
        total_lines = int(total_lines)

    full_file = any(
        _is_truthy(_first_present(source, _FULL_FILE_KEYS))
        for source in (args, result)
    )

    start = _first_present(args, _START_KEYS) or _first_present(
        result, _RESULT_START_KEYS
    )
    start_line = int(start) if start is not None else 1

    end = _first_present(args, _END_KEYS) or _first_present(result, _RESULT_END_KEYS)
    contents = result.get("contents")
    content_lines = _line_count_from_contents(contents) if contents is not None else 0

    if end is not None:
        end_line = int(end)
    else:
        limit = _first_present(args, _LIMIT_KEYS)
        returned_lines = _first_present(result, ("totalLines",))

        if content_lines > 0:
            end_line = start_line + content_lines - 1
        elif limit is not None:
            end_line = start_line + int(limit) - 1
        elif returned_lines is not None:
            end_line = start_line + int(returned_lines) - 1
        elif _is_metadata_only_full_read(args, result, total_lines, content_lines):
            full_file = True
            end_line = total_lines if total_lines is not None else start_line
        else:
            end_line = start_line

    if total_lines is not None and not full_file:
        end_line = min(end_line, total_lines)

    if (
        not full_file
        and total_lines is not None
        and start_line <= 1
        and end_line >= total_lines
    ):
        full_file = True

    usage = FileContextUsage()
    if full_file:
        usage.full_file = True
    elif end_line >= start_line:
        usage.lines.update(range(start_line, end_line + 1))

    return file_path, usage


def extract_search_context(
    tool_data: Dict[str, Any],
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


def _edit_was_applied(tool_name: str, result: Dict[str, Any]) -> bool:
    if _is_truthy(result.get("rejected")):
        return False
    if tool_name == "delete_file":
        return _is_truthy(result.get("fileDeletedSuccessfully"))
    if "isApplied" in result and not _is_truthy(result.get("isApplied")):
        return False
    return True


def extract_edit_context(
    tool_data: Dict[str, Any],
) -> Optional[Tuple[str, bool]]:
    tool_name = tool_data.get("name")
    if tool_name not in EDIT_TOOL_NAMES:
        return None

    args = _parse_tool_args(tool_data)
    result = _parse_tool_result(tool_data)
    if not _edit_was_applied(tool_name, result):
        return None

    file_path = _first_present(args, _PATH_KEYS)
    if not isinstance(file_path, str) or not file_path:
        return None

    return file_path, tool_name == "delete_file"


def _merge_edit_usage(
    target: Dict[str, FileContextUsage],
    file_path: str,
    project_root: Optional[str],
    bubble_index: int,
    *,
    deleted: bool = False,
) -> None:
    rel_path = _normalize_path(file_path, project_root)
    if not rel_path:
        return

    if project_root and os.path.isabs(file_path.replace("\\", "/")):
        abs_path = os.path.normpath(file_path.replace("\\", "/"))
        root = os.path.normpath(project_root)
        try:
            if os.path.commonpath([abs_path, root]) != root:
                return
        except ValueError:
            return

    existing = target.setdefault(rel_path, FileContextUsage())
    existing.edit_hits += 1
    if existing.last_edit_bubble_index is None:
        existing.last_edit_bubble_index = bubble_index
    else:
        existing.last_edit_bubble_index = max(
            existing.last_edit_bubble_index,
            bubble_index,
        )
    if deleted:
        existing.deleted = True


def _merge_usage(
    target: Dict[str, FileContextUsage],
    file_path: str,
    usage: FileContextUsage,
    project_root: Optional[str],
    bubble_index: int,
) -> None:
    rel_path = _normalize_path(file_path, project_root)
    if not rel_path:
        return

    if project_root and os.path.isabs(file_path.replace("\\", "/")):
        abs_path = os.path.normpath(file_path.replace("\\", "/"))
        root = os.path.normpath(project_root)
        try:
            if os.path.commonpath([abs_path, root]) != root:
                return
        except ValueError:
            return

    existing = target.setdefault(rel_path, FileContextUsage())
    existing.hits += 1
    if existing.last_bubble_index is None:
        existing.last_bubble_index = bubble_index
    else:
        existing.last_bubble_index = max(existing.last_bubble_index, bubble_index)
    if usage.full_file:
        existing.full_file = True
        existing.lines.clear()
    elif not existing.full_file:
        existing.lines.update(usage.lines)


def collect_context_usage(
    messages: List[Dict],
    project_root: Optional[str] = None,
    *,
    min_bubble_index: Optional[int] = None,
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
            edit_usage = extract_edit_context(tool_data)
            if edit_usage:
                file_path, deleted = edit_usage
                _merge_edit_usage(
                    usage_by_file,
                    file_path,
                    project_root,
                    bubble_index,
                    deleted=deleted,
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
                )
            continue

        for file_path, usage in extract_search_context(tool_data):
            _merge_usage(
                usage_by_file,
                file_path,
                usage,
                project_root,
                bubble_index,
            )

    return usage_by_file
