"""Build context trees from Cursor dialog messages."""

from __future__ import annotations

from typing import Dict, List, Optional

from context_reviewer.agents.cursor.content_lookup import ContentLookup
from context_reviewer.agents.cursor.extractor import collect_context_usage
from context_reviewer.context.models import ContextTreeResult

_NO_USER_MESSAGES = "(no user messages in dialog)"
_NO_AGENT_MESSAGES = "(no agent messages after last user message)"


def last_user_bubble_index(messages: List[Dict]) -> Optional[int]:
    """Return the index of the last user message (type 1), or None."""
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("type") == 1:
            return index
    return None


def build_context_tree(
    messages: List[Dict],
    project_root: Optional[str] = None,
    *,
    last_turn: bool = False,
    content_lookup: Optional[ContentLookup] = None,
) -> ContextTreeResult:
    """Collect context usage, optionally limited to the current agent turn."""
    if not last_turn:
        return ContextTreeResult(
            collect_context_usage(
                messages,
                project_root,
                content_lookup=content_lookup,
            ),
            len(messages),
        )

    cutoff = last_user_bubble_index(messages)
    if cutoff is None:
        return ContextTreeResult({}, 0, empty_message=_NO_USER_MESSAGES)
    if cutoff >= len(messages) - 1:
        return ContextTreeResult({}, 0, empty_message=_NO_AGENT_MESSAGES)

    post_cutoff_bubbles = len(messages) - cutoff - 1
    return ContextTreeResult(
        collect_context_usage(
            messages,
            project_root,
            min_bubble_index=cutoff,
            content_lookup=content_lookup,
        ),
        post_cutoff_bubbles,
        recency_bubble_offset=cutoff + 1,
    )
