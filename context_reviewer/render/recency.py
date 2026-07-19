"""Recency indicators for context tree output."""

from __future__ import annotations

_RECENCY_DOT_SLOTS = 5


def normalize_bubble_percent(
    last_bubble_index: int,
    total_bubbles: int,
    *,
    bubble_offset: int = 0,
) -> int:
    """Map a bubble index to 0-100 across a conversation window."""
    if total_bubbles <= 1:
        return 0
    relative_index = last_bubble_index - bubble_offset
    return round(relative_index / (total_bubbles - 1) * 100)


def recency_filled_dots(bubble_percent: int) -> int:
    """Map 0-100 conversation position to 1-5 filled dot slots (quintiles).

    The first quintile (0-20%) always shows one dot so early context use is visible.
    """
    return min(_RECENCY_DOT_SLOTS, max(1, (bubble_percent + 19) // 20))


def recency_dot_slots(bubble_percent: int) -> str:
    """Render fixed-width dot slots without brackets, e.g. ``· · ·    ``."""
    filled = recency_filled_dots(bubble_percent)
    slots = ["·" if index < filled else " " for index in range(_RECENCY_DOT_SLOTS)]
    return " ".join(slots)


def format_recency_dots(bubble_percent: int) -> str:
    """Render fixed-width recency scale, e.g. ``[· · ·    ]`` for 3 of 5 slots."""
    return f"[{recency_dot_slots(bubble_percent)}]"
