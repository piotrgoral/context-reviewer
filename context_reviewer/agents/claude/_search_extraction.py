"""Grep-tool search extraction from Claude Code tool payloads."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from context_reviewer.context.models import FileContextUsage

SEARCH_TOOL_NAMES = frozenset({"Grep"})

_RIPGREP_LINE_RE = re.compile(
    r"^(?:(?P<file>[^:]+):)?(?P<line>\d+)(?::|\|)(?P<content>.*)$"
)


def is_search_tool(tool_name: Optional[str]) -> bool:
    return tool_name in SEARCH_TOOL_NAMES


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_grep_stdout(stdout: str, default_path: str) -> List[Tuple[str, int]]:
    matches: List[Tuple[str, int]] = []
    for raw_line in stdout.splitlines():
        line = raw_line.rstrip("\n")
        if not line or line.startswith("Binary file"):
            continue
        match = _RIPGREP_LINE_RE.match(line)
        if not match:
            continue
        file_path = match.group("file") or default_path
        line_number = _coerce_int(match.group("line"))
        if line_number is None:
            continue
        matches.append((file_path, line_number))
    return matches


def extract_search_context(
    tool_data: Dict[str, Any],
) -> List[Tuple[str, FileContextUsage]]:
    tool_name = tool_data.get("name")
    if tool_name not in SEARCH_TOOL_NAMES:
        return []

    tool_input = tool_data.get("input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    result = tool_data.get("result")
    if not isinstance(result, dict):
        result = {}

    default_path = tool_input.get("path") or tool_input.get("glob") or ""
    if not isinstance(default_path, str):
        default_path = ""

    stdout = result.get("stdout")
    if not isinstance(stdout, str) or not stdout.strip():
        return []

    by_file: Dict[str, FileContextUsage] = {}
    for file_path, line_number in _parse_grep_stdout(stdout, default_path):
        if not file_path:
            continue
        usage = by_file.setdefault(file_path, FileContextUsage())
        usage.lines.add(line_number)
    return list(by_file.items())
