"""
Read-tool line-range extraction from Cursor tool-call payloads.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from context_reviewer.context.models import FileContextUsage

from ._shared import (
    _END_KEYS,
    _FULL_FILE_KEYS,
    _LIMIT_KEYS,
    _PATH_KEYS,
    _RESULT_END_KEYS,
    _RESULT_START_KEYS,
    _START_KEYS,
    _first_present,
    _is_truthy,
    _parse_tool_args,
    _parse_tool_result,
)

READ_CONTEXT_TOOL_NAMES = frozenset({"read_file", "read_file_v2"})


def is_read_context_tool(tool_name: Optional[str]) -> bool:
    return tool_name in READ_CONTEXT_TOOL_NAMES


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
