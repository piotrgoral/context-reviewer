"""Read-tool line-range extraction from Claude Code tool payloads."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from context_reviewer.context.models import FileContextUsage

READ_TOOL_NAMES = frozenset({"Read"})


def is_read_tool(tool_name: Optional[str]) -> bool:
    return tool_name in READ_TOOL_NAMES


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _line_count_from_contents(contents: str) -> int:
    if not contents:
        return 0
    return len(contents.splitlines())


def _parse_tab_numbered_content(text: str) -> Tuple[int, int]:
    """Return (start_line, line_count) from Claude tab-numbered read output."""
    lines = text.splitlines()
    if not lines:
        return 1, 0

    numbers = []
    for line in lines:
        if "\t" not in line:
            continue
        prefix = line.split("\t", 1)[0].strip()
        number = _coerce_int(prefix)
        if number is not None:
            numbers.append(number)

    if not numbers:
        return 1, len(lines)
    return numbers[0], len(numbers)


def extract_read_context(
    tool_data: Dict[str, Any],
) -> Optional[Tuple[str, FileContextUsage]]:
    tool_name = tool_data.get("name")
    if tool_name not in READ_TOOL_NAMES:
        return None

    tool_input = tool_data.get("input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    result = tool_data.get("result")
    if not isinstance(result, dict):
        result = {}

    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        file_info = result.get("file")
        if isinstance(file_info, dict):
            candidate = file_info.get("filePath")
            if isinstance(candidate, str):
                file_path = candidate
    if not isinstance(file_path, str) or not file_path:
        return None

    usage = FileContextUsage()
    offset = _coerce_int(tool_input.get("offset"))
    limit = _coerce_int(tool_input.get("limit"))

    file_info = result.get("file")
    if isinstance(file_info, dict):
        start_line = _coerce_int(file_info.get("startLine"))
        num_lines = _coerce_int(file_info.get("numLines"))
        total_lines = _coerce_int(file_info.get("totalLines"))
        content = file_info.get("content")
        if start_line is not None and num_lines is not None and num_lines > 0:
            usage.lines.update(range(start_line, start_line + num_lines))
        elif isinstance(content, str):
            start, count = _parse_tab_numbered_content(content)
            if count > 0:
                usage.lines.update(range(start, start + count))
        if total_lines is not None and num_lines is not None and total_lines == num_lines:
            if offset in (None, 1) and limit is None:
                usage.full_file = True
        return file_path, usage

    if offset is not None or limit is not None:
        start = offset if offset is not None else 1
        count = limit if limit is not None else 0
        if count > 0:
            usage.lines.update(range(start, start + count))
        return file_path, usage

    raw_content = result.get("content")
    if isinstance(raw_content, str) and raw_content.strip():
        start, count = _parse_tab_numbered_content(raw_content)
        if count > 0:
            usage.lines.update(range(start, start + count))
        return file_path, usage

    return file_path, usage
