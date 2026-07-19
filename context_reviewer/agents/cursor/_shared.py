"""
Generic tool-payload parsing helpers shared by read/edit/search extraction.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Optional, Set

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
_PATCH_CONTENT_KEYS = ("patch", "input", "contents", "unifiedPatch", "diff")
_MULTIEDIT_KEYS = ("edits", "Edits")
_STREAMING_CONTENT_KEYS = ("streamingContent", "streaming_content")


def _lines_from_range(start_line: int, end_line: int) -> Set[int]:
    if end_line < start_line:
        return set()
    return set(range(start_line, end_line + 1))


def _extract_line_range_from_dict(data: Dict[str, Any]) -> Set[int]:
    start = _first_present(data, _START_KEYS)
    end = _first_present(data, _END_KEYS)
    if start is None and end is None:
        return set()
    start_line = int(start) if start is not None else 1
    end_line = int(end) if end is not None else start_line
    return _lines_from_range(start_line, end_line)


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
