"""Load and normalize Claude Code session JSONL into review bubbles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .utils import is_meta_user_content

BUBBLE_TYPE_USER = "user"
BUBBLE_TYPE_ASSISTANT = "assistant"


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                yield record


def _pending_tool_uses(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    message = record.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []

    pending: List[Dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_use":
            continue
        tool_id = block.get("id")
        name = block.get("name")
        tool_input = block.get("input")
        if not isinstance(tool_id, str) or not isinstance(name, str):
            continue
        if not isinstance(tool_input, dict):
            tool_input = {}
        pending.append(
            {
                "id": tool_id,
                "name": name,
                "input": tool_input,
            }
        )
    return pending


def _tool_results_from_user(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    message = record.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []

    results: List[Dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_result":
            continue
        tool_use_id = block.get("tool_use_id")
        if not isinstance(tool_use_id, str):
            continue
        results.append(
            {
                "tool_use_id": tool_use_id,
                "content": block.get("content"),
                "is_error": bool(block.get("is_error")),
            }
        )
    return results


def _user_prompt_text(record: Dict[str, Any]) -> Optional[str]:
    message = record.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        text = content.strip()
        if not text or is_meta_user_content(text):
            return None
        return text
    return None


def _normalize_records(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    pending_by_id: Dict[str, Dict[str, Any]] = {}
    bubbles: List[Dict[str, Any]] = []

    for record in records:
        line_type = record.get("type")
        if line_type == "assistant":
            for pending in _pending_tool_uses(record):
                pending_by_id[pending["id"]] = pending
            continue

        if line_type != "user":
            continue

        tool_results = _tool_results_from_user(record)
        if tool_results:
            tool_use_result = record.get("toolUseResult")
            if not isinstance(tool_use_result, dict):
                tool_use_result = {}
            for result in tool_results:
                pending = pending_by_id.pop(result["tool_use_id"], None)
                if pending is None:
                    continue
                bubbles.append(
                    {
                        "type": BUBBLE_TYPE_ASSISTANT,
                        "text": None,
                        "tool_data": {
                            "name": pending["name"],
                            "input": pending["input"],
                            "result": tool_use_result,
                            "status": "completed",
                        },
                    }
                )
            continue

        prompt = _user_prompt_text(record)
        if prompt is not None:
            bubbles.append(
                {
                    "type": BUBBLE_TYPE_USER,
                    "text": prompt,
                    "tool_data": None,
                }
            )

    return bubbles


def load_session_bubbles(session_path: Path) -> List[Dict[str, Any]]:
    """Load normalized bubbles from one session JSONL file."""
    return _normalize_records(_iter_jsonl(session_path))


def load_session_messages(
    session_path: Path,
    *,
    include_subagents: bool = True,
) -> List[Dict[str, Any]]:
    """Load main session bubbles and append subagent transcript bubbles."""
    bubbles = load_session_bubbles(session_path)
    if not include_subagents:
        return bubbles

    session_id = session_path.stem
    project_dir = session_path.parent
    subagents_root = project_dir / session_id / "subagents"
    if not subagents_root.is_dir():
        return bubbles

    for subagent_path in sorted(subagents_root.glob("agent-*.jsonl")):
        bubbles.extend(load_session_bubbles(subagent_path))
    return bubbles
