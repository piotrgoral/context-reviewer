"""Edit-tool line usage extraction from Claude Code tool payloads."""

from __future__ import annotations

import difflib
from typing import Any, Dict, List, Optional, Set, Tuple

from context_reviewer.context.models import FileContextUsage

EDIT_TOOL_NAMES = frozenset({"Edit", "Write", "NotebookEdit"})


def is_edit_tool(tool_name: Optional[str]) -> bool:
    return tool_name in EDIT_TOOL_NAMES


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _lines_from_structured_diff(structured_diff: Any) -> Set[int]:
    lines: Set[int] = set()
    if not isinstance(structured_diff, list):
        return lines

    for hunk in structured_diff:
        if not isinstance(hunk, dict):
            continue
        start = _coerce_int(hunk.get("startLine") or hunk.get("line"))
        count = _coerce_int(hunk.get("lineCount") or hunk.get("count"))
        if start is None:
            continue
        if count is None or count <= 0:
            lines.add(start)
            continue
        lines.update(range(start, start + count))
    return lines


def _lines_from_content_diff(original: str, updated: str) -> Set[int]:
    original_lines = original.splitlines(keepends=True)
    updated_lines = updated.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(None, original_lines, updated_lines)
    lines: Set[int] = set()
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag in {"replace", "insert"}:
            start = j1 + 1
            end = j2
            if end <= j1:
                lines.add(start)
            else:
                lines.update(range(start, end + 1))
        elif tag == "delete":
            start = i1 + 1
            end = i2
            if end <= i1:
                lines.add(start)
            else:
                lines.update(range(start, end + 1))
    return lines


def _line_count(content: str) -> int:
    if not content:
        return 0
    return len(content.splitlines())


def extract_edit_context(
    tool_data: Dict[str, Any],
) -> Optional[Tuple[str, FileContextUsage]]:
    tool_name = tool_data.get("name")
    if tool_name not in EDIT_TOOL_NAMES:
        return None

    tool_input = tool_data.get("input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    result = tool_data.get("result")
    if not isinstance(result, dict):
        result = {}

    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        candidate = result.get("filePath")
        if isinstance(candidate, str):
            file_path = candidate
    if not isinstance(file_path, str) or not file_path:
        return None

    usage = FileContextUsage()
    result_type = result.get("type")

    if tool_name == "Write" or result_type == "create":
        content = tool_input.get("content")
        if not isinstance(content, str):
            content = result.get("content")
        if isinstance(content, str) and content:
            usage.edit_full_file = True
            usage.edit_lines = set(range(1, _line_count(content) + 1))
        else:
            usage.edit_full_file = True
        return file_path, usage

    structured = result.get("structuredDiff")
    if structured is not None:
        usage.edit_lines = _lines_from_structured_diff(structured)
        if usage.edit_lines:
            return file_path, usage

    original = result.get("originalFile")
    updated = result.get("content")
    if isinstance(original, str) and isinstance(updated, str):
        usage.edit_lines = _lines_from_content_diff(original, updated)
        if usage.edit_lines:
            return file_path, usage

    old_string = tool_input.get("old_string")
    new_string = tool_input.get("new_string")
    if isinstance(old_string, str) and isinstance(new_string, str):
        if old_string == new_string:
            return file_path, usage
        usage.edit_lines = _lines_from_content_diff(old_string, new_string)
        if usage.edit_lines:
            return file_path, usage
        usage.edit_full_file = True
        return file_path, usage

    if result_type == "update":
        content = result.get("content")
        if isinstance(content, str) and content:
            usage.edit_full_file = True
            usage.edit_lines = set(range(1, _line_count(content) + 1))
            return file_path, usage

    return file_path, usage
