"""
Edit-tool line usage extraction (diff/patch math) from Cursor tool-call payloads.
"""

from __future__ import annotations

import difflib
import re
from typing import Any, Dict, Optional, Set, Tuple

from context_reviewer.agents.cursor.content_lookup import ContentLookup
from context_reviewer.context.models import FileContextUsage

from ._shared import (
    _MULTIEDIT_KEYS,
    _PATCH_CONTENT_KEYS,
    _PATH_KEYS,
    _STREAMING_CONTENT_KEYS,
    _extract_line_range_from_dict,
    _first_present,
    _is_truthy,
    _parse_tool_args,
    _parse_tool_result,
)

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

_PATCH_HUNK_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@",
    re.MULTILINE,
)


def is_edit_tool(tool_name: Optional[str]) -> bool:
    return tool_name in EDIT_TOOL_NAMES


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_patch_lines(patch_text: str) -> Set[int]:
    lines: Set[int] = set()
    for match in _PATCH_HUNK_RE.finditer(patch_text):
        new_start = int(match.group(3))
        new_count = int(match.group(4)) if match.group(4) is not None else 1
        if new_count <= 0:
            lines.add(new_start)
            continue
        lines.update(range(new_start, new_start + new_count))
    return lines


def _extract_multiedit_lines(args: Dict[str, Any]) -> Set[int]:
    edits = None
    for key in _MULTIEDIT_KEYS:
        candidate = args.get(key)
        if isinstance(candidate, list):
            edits = candidate
            break
    if not edits:
        return set()

    lines: Set[int] = set()
    for edit in edits:
        if isinstance(edit, dict):
            lines.update(_extract_line_range_from_dict(edit))
    return lines


def _extract_lines_from_result_diff(result: Dict[str, Any]) -> Set[int]:
    diff = result.get("diff")
    if not isinstance(diff, dict):
        return set()
    chunks = diff.get("chunks")
    if not isinstance(chunks, list):
        return set()

    lines: Set[int] = set()
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        new_start = _coerce_int(chunk.get("newStart"))
        new_lines = _coerce_int(chunk.get("newLines"))
        old_start = _coerce_int(chunk.get("oldStart"))
        old_lines = _coerce_int(chunk.get("oldLines"))

        if new_start is not None and new_lines is not None and new_lines > 0:
            lines.update(range(new_start, new_start + new_lines))
        elif old_start is not None and old_lines is not None and old_lines > 0:
            lines.update(range(old_start, old_start + old_lines))
    return lines


def _extract_lines_from_content_diff(before: str, after: str) -> Set[int]:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    lines: Set[int] = set()
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, before_lines, after_lines
    ).get_opcodes():
        if tag == "equal":
            continue
        if tag in {"replace", "insert"} and j2 > j1:
            lines.update(range(j1 + 1, j2 + 1))
        elif tag == "delete" and i2 > i1:
            lines.update(range(i1 + 1, i2 + 1))
    return lines


def _extract_edit_file_v2_content_lines(
    args: Dict[str, Any],
    result: Dict[str, Any],
    content_lookup: ContentLookup,
) -> Set[int]:
    before_id = result.get("beforeContentId")
    if not isinstance(before_id, str) or not before_id:
        return set()

    before = content_lookup(before_id)
    if before is None:
        return set()

    streaming = _first_present(args, _STREAMING_CONTENT_KEYS)
    if isinstance(streaming, str) and streaming:
        after = streaming
    else:
        after_id = result.get("afterContentId")
        if not isinstance(after_id, str) or not after_id:
            return set()
        after = content_lookup(after_id)
        if after is None:
            return set()

    return _extract_lines_from_content_diff(before, after)


def _extract_edit_line_usage(
    tool_name: str,
    args: Dict[str, Any],
    result: Dict[str, Any],
    *,
    content_lookup: Optional[ContentLookup] = None,
) -> FileContextUsage:
    usage = FileContextUsage()
    if tool_name == "delete_file":
        usage.deleted = True
        return usage
    if tool_name == "write":
        usage.edit_full_file = True
        return usage
    if tool_name == "apply_patch":
        patch_text = _first_present(args, _PATCH_CONTENT_KEYS)
        if isinstance(patch_text, str):
            usage.edit_lines.update(_extract_patch_lines(patch_text))
    elif tool_name == "MultiEdit":
        usage.edit_lines.update(_extract_multiedit_lines(args))
    elif tool_name in {"edit_file_v2", "edit_file"}:
        usage.edit_lines.update(_extract_line_range_from_dict(args))

    if not usage.edit_lines:
        usage.edit_lines.update(_extract_lines_from_result_diff(result))
    if (
        not usage.edit_lines
        and tool_name == "edit_file_v2"
        and content_lookup is not None
    ):
        usage.edit_lines.update(
            _extract_edit_file_v2_content_lines(args, result, content_lookup)
        )
    return usage


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
    *,
    content_lookup: Optional[ContentLookup] = None,
) -> Optional[Tuple[str, FileContextUsage]]:
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

    usage = _extract_edit_line_usage(
        tool_name,
        args,
        result,
        content_lookup=content_lookup,
    )
    return file_path, usage
