"""Shared helpers and paths for Claude Code tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = "/tmp/project"
SESSION_ID = "test-session-id"
FIXTURES = Path(__file__).parent / "fixtures" / "claude"
SESSION = FIXTURES / f"{SESSION_ID}.jsonl"


def user_bubble(text: str) -> Dict[str, Any]:
    return {"type": "user", "text": text, "tool_data": None}


def read_bubble(
    rel_path: str,
    *,
    offset: int = 1,
    limit: int = 3,
    start_line: int = 1,
    num_lines: int = 3,
    total_lines: int = 100,
) -> Dict[str, Any]:
    file_path = f"{PROJECT_ROOT}/{rel_path}"
    return {
        "type": "assistant",
        "text": None,
        "tool_data": {
            "name": "Read",
            "input": {"file_path": file_path, "offset": offset, "limit": limit},
            "result": {
                "file": {
                    "filePath": file_path,
                    "startLine": start_line,
                    "numLines": num_lines,
                    "totalLines": total_lines,
                    "content": "\n".join(
                        f"{line}\tcontent line {line}" for line in range(start_line, start_line + num_lines)
                    ),
                }
            },
            "status": "completed",
        },
    }


def edit_bubble(rel_path: str, *, lines: Optional[List[int]] = None) -> Dict[str, Any]:
    file_path = f"{PROJECT_ROOT}/{rel_path}"
    structured_diff = []
    if lines:
        for line in sorted(lines):
            structured_diff.append({"startLine": line, "lineCount": 1})
    return {
        "type": "assistant",
        "text": None,
        "tool_data": {
            "name": "Edit",
            "input": {
                "file_path": file_path,
                "old_string": "before",
                "new_string": "after",
            },
            "result": {
                "type": "update",
                "filePath": file_path,
                "structuredDiff": structured_diff or [{"startLine": 10, "lineCount": 1}],
            },
            "status": "completed",
        },
    }


def write_bubble(rel_path: str, *, line_count: int = 5) -> Dict[str, Any]:
    file_path = f"{PROJECT_ROOT}/{rel_path}"
    content = "\n".join(f"line {index}" for index in range(1, line_count + 1))
    return {
        "type": "assistant",
        "text": None,
        "tool_data": {
            "name": "Write",
            "input": {"file_path": file_path, "content": content},
            "result": {"type": "create", "filePath": file_path, "content": content},
            "status": "completed",
        },
    }


def sample_messages(*, include_follow_up: bool = True) -> List[Dict[str, Any]]:
    messages = [
        read_bubble("src/app.py"),
        user_bubble("please refactor this module"),
        edit_bubble("src/app.py", lines=[10, 11]),
        write_bubble("src/new.py"),
    ]
    if include_follow_up:
        messages.append(read_bubble("src/other.py", offset=5, limit=2, start_line=5, num_lines=2))
    return messages
