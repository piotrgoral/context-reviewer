"""
Extract search/read tool results from Cursor database payloads.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

SEARCH_TOOL_NAMES = frozenset({"ripgrep_raw_search", "grep", "rg", "grep_search"})
WORKSPACE_SEARCH_TOOL_NAMES = frozenset({"ripgrep_raw_search", "grep", "rg"})
CODE_SEARCH_TOOL_NAMES = frozenset({"codebase_search", "semantic_search_full"})
RIPgrep_TOOL_NAME = "ripgrep_raw_search"


@dataclass(frozen=True)
class SearchMatch:
    line_number: int
    content: str
    file: str = ""


RipgrepMatch = SearchMatch


def is_search_tool(tool_name: Optional[str]) -> bool:
    return tool_name in SEARCH_TOOL_NAMES


def is_code_search_tool(tool_name: Optional[str]) -> bool:
    return tool_name in CODE_SEARCH_TOOL_NAMES


def _read_varint(data: bytes, index: int) -> Tuple[int, int]:
    value = 0
    shift = 0
    while index < len(data):
        byte = data[index]
        value |= (byte & 0x7F) << shift
        index += 1
        if not (byte & 0x80):
            return value, index
        shift += 7
    raise ValueError("truncated varint")


def _read_length_delimited(data: bytes, index: int) -> Tuple[bytes, int]:
    length, index = _read_varint(data, index)
    end = index + length
    return data[index:end], end


def extract_line_matches_from_binary(data: bytes) -> List[Tuple[int, str]]:
    """
    Scan Cursor's search toolCallBinary payload for line/content pairs.

    Cursor encodes content-mode matches as repeated protobuf fields:
    0x08 <lineNumber> 0x12 <content>
    """
    matches: List[Tuple[int, str]] = []
    index = 0
    while index < len(data) - 3:
        if data[index] != 0x08:
            index += 1
            continue
        try:
            line_number, next_index = _read_varint(data, index + 1)
            if next_index >= len(data) or data[next_index] != 0x12:
                index += 1
                continue
            content, after_content = _read_length_delimited(data, next_index + 1)
            text = content.decode("utf-8", errors="replace")
            if len(text) > 2:
                matches.append((line_number, text))
            index = after_content
        except (ValueError, UnicodeDecodeError):
            index += 1
    return matches


def _parse_tool_result(result: Any) -> Optional[Any]:
    if isinstance(result, (dict, list)):
        return result
    if isinstance(result, str) and result:
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return None
    return None


def _file_label_from_resource(resource: Any) -> str:
    if not isinstance(resource, str) or not resource:
        return ""
    if resource.startswith("file://"):
        path = unquote(urlparse(resource).path)
        return path.rsplit("/", 1)[-1] if path else resource
    return resource.rsplit("/", 1)[-1]


def _extract_matches_from_file_groups(file_groups: Any) -> List[SearchMatch]:
    matches: List[SearchMatch] = []
    if not isinstance(file_groups, list):
        return matches

    for file_match in file_groups:
        if not isinstance(file_match, dict):
            continue
        file_path = str(
            file_match.get("file")
            or file_match.get("absolutePath")
            or file_match.get("relativePath")
            or ""
        )
        for line_match in file_match.get("matches", []):
            if not isinstance(line_match, dict):
                continue
            line_number = line_match.get("lineNumber")
            line_content = line_match.get("content")
            if line_number is None or line_content is None:
                continue
            matches.append(
                SearchMatch(
                    line_number=int(line_number),
                    content=str(line_content),
                    file=file_path,
                )
            )
    return matches


def _extract_matches_from_workspace_results(
    workspace_results: Any,
) -> List[SearchMatch]:
    matches: List[SearchMatch] = []
    if not isinstance(workspace_results, dict):
        return matches

    for workspace_data in workspace_results.values():
        if not isinstance(workspace_data, dict):
            continue
        content = workspace_data.get("content")
        if isinstance(content, dict):
            matches.extend(_extract_matches_from_file_groups(content.get("matches", [])))
    return matches


def extract_matches_from_grep_search_result(result_data: Any) -> List[SearchMatch]:
    """Extract line matches from grep_search internal result payloads."""
    if not isinstance(result_data, dict):
        return []

    internal = result_data.get("internal")
    if not isinstance(internal, dict):
        return []

    matches: List[SearchMatch] = []
    for file_result in internal.get("results", []):
        if not isinstance(file_result, dict):
            continue
        file_path = _file_label_from_resource(file_result.get("resource"))
        for hit in file_result.get("results", []):
            if not isinstance(hit, dict):
                continue
            match = hit.get("match")
            if not isinstance(match, dict):
                continue
            preview_text = match.get("previewText")
            range_locations = match.get("rangeLocations")
            if preview_text is None or not isinstance(range_locations, list):
                continue
            if not range_locations or not isinstance(range_locations[0], dict):
                continue
            source = range_locations[0].get("source")
            if not isinstance(source, dict):
                continue
            line_number = source.get("startLineNumber")
            if line_number is None:
                continue
            matches.append(
                SearchMatch(
                    line_number=int(line_number),
                    content=str(preview_text),
                    file=file_path,
                )
            )
    return matches


def _code_results_from_payload(result_data: Any) -> List[Any]:
    if not isinstance(result_data, dict):
        return []
    code_results = result_data.get("codeResults")
    return code_results if isinstance(code_results, list) else []


def _should_skip_code_result_line(line: Dict[str, Any], line_number: Any, text: str) -> bool:
    if not text:
        return True
    if isinstance(line_number, float) and line_number != int(line_number):
        return True
    if line.get("isSignature") and "..." in text:
        return True
    return False


def extract_matches_from_code_results(result_data: Any) -> List[SearchMatch]:
    """Extract line matches from codebase_search / semantic_search_full codeResults."""
    matches: List[SearchMatch] = []
    for item in _code_results_from_payload(result_data):
        if not isinstance(item, dict):
            continue
        code_block = item.get("codeBlock")
        if not isinstance(code_block, dict):
            continue
        file_path = str(code_block.get("relativeWorkspacePath") or "")
        for line in code_block.get("detailedLines") or []:
            if not isinstance(line, dict):
                continue
            line_number = line.get("lineNumber")
            text = line.get("text")
            if line_number is None or text is None:
                continue
            if _should_skip_code_result_line(line, line_number, str(text)):
                continue
            matches.append(
                SearchMatch(
                    line_number=int(line_number),
                    content=str(text),
                    file=file_path,
                )
            )
    return matches


def extract_code_search_matches(tool_data: Dict[str, Any]) -> List[SearchMatch]:
    """Resolve semantic search matches from result JSON or params.codeResults."""
    if not tool_data or not is_code_search_tool(tool_data.get("name")):
        return []

    for field in ("result", "params"):
        result_data = _parse_tool_result(tool_data.get(field))
        if result_data is None:
            continue
        matches = extract_matches_from_code_results(result_data)
        if matches:
            return matches
    return []


def extract_matches_from_json_result(result_data: Any) -> List[SearchMatch]:
    """Extract line matches from workspace-style search JSON result payloads."""
    if not isinstance(result_data, dict):
        return []

    payload = result_data
    if "success" in result_data and isinstance(result_data["success"], dict):
        payload = result_data["success"]

    matches = _extract_matches_from_workspace_results(payload.get("workspaceResults"))

    active_editor = payload.get("activeEditorResult")
    if isinstance(active_editor, dict):
        content = active_editor.get("content")
        if isinstance(content, dict):
            matches.extend(_extract_matches_from_file_groups(content.get("matches", [])))

    return matches


def _default_file_from_additional(additional_data: Any) -> str:
    if not isinstance(additional_data, dict):
        return ""
    top_files = additional_data.get("topFiles")
    if isinstance(top_files, list) and top_files:
        first = top_files[0]
        if isinstance(first, dict):
            return str(first.get("uri", ""))
    return str(additional_data.get("path", ""))


def extract_search_matches(tool_data: Dict[str, Any]) -> List[SearchMatch]:
    """
    Resolve search-tool matches from result JSON, toolCallBinary, or additionalData.
    """
    if not tool_data:
        return []

    tool_name = tool_data.get("name")
    if not is_search_tool(tool_name):
        return []

    result_data = _parse_tool_result(tool_data.get("result"))
    if result_data is not None:
        if tool_name == "grep_search":
            grep_search_matches = extract_matches_from_grep_search_result(result_data)
            if grep_search_matches:
                return grep_search_matches
        else:
            json_matches = extract_matches_from_json_result(result_data)
            if json_matches:
                return json_matches

    if tool_name not in WORKSPACE_SEARCH_TOOL_NAMES:
        return []

    tool_call_binary = tool_data.get("toolCallBinary")
    if tool_call_binary:
        try:
            raw = base64.b64decode(tool_call_binary)
            binary_matches = extract_line_matches_from_binary(raw)
            if binary_matches:
                additional = tool_data.get("additionalData") or {}
                default_file = _default_file_from_additional(additional)
                return [
                    SearchMatch(line_number=line, content=text, file=default_file)
                    for line, text in binary_matches
                ]
        except (ValueError, TypeError):
            pass

    return []


def extract_ripgrep_matches(tool_data: Dict[str, Any]) -> List[SearchMatch]:
    """Backward-compatible alias for extract_search_matches."""
    return extract_search_matches(tool_data)
