"""Read/edit activity suffixes and file detail formatting."""

from __future__ import annotations

from context_reviewer.context.models import FileContextUsage
from context_reviewer.render.lines import iter_line_range_parts
from context_reviewer.render.recency import format_recency_dots, normalize_bubble_percent
from context_reviewer.render.terminal import ansi

_MAX_LINE_RANGE_PARTS = 8
_ANSI_GREEN = "92"
_ANSI_ORANGE = "38;5;208"


def format_read_activity_suffix(
    file_usage: FileContextUsage,
    total_bubbles: int = 0,
    *,
    recency_bubble_offset: int = 0,
) -> str:
    if file_usage.hits <= 0:
        return ""
    parts = [f"[{file_usage.hits} read]"]
    if file_usage.last_bubble_index is not None and total_bubbles > 1:
        bubble_percent = normalize_bubble_percent(
            file_usage.last_bubble_index,
            total_bubbles,
            bubble_offset=recency_bubble_offset,
        )
        parts.append(format_recency_dots(bubble_percent))
    return " ".join(parts)


def format_edit_activity_suffix(
    file_usage: FileContextUsage,
    total_bubbles: int = 0,
    *,
    recency_bubble_offset: int = 0,
) -> str:
    if file_usage.edit_hits <= 0:
        return ""
    edit_label = "edit" if file_usage.edit_hits == 1 else "edits"
    parts = [f"[{file_usage.edit_hits} {edit_label}]"]
    if file_usage.last_edit_bubble_index is not None and total_bubbles > 1:
        bubble_percent = normalize_bubble_percent(
            file_usage.last_edit_bubble_index,
            total_bubbles,
            bubble_offset=recency_bubble_offset,
        )
        parts.append(format_recency_dots(bubble_percent))
    return " ".join(parts)


def format_activity_suffix(
    file_usage: FileContextUsage,
    total_bubbles: int = 0,
    *,
    recency_bubble_offset: int = 0,
) -> str:
    """Format read/edit counts and recency in order: read, read dots, edit, edit dots."""
    parts = [
        format_read_activity_suffix(
            file_usage,
            total_bubbles,
            recency_bubble_offset=recency_bubble_offset,
        ),
        format_edit_activity_suffix(
            file_usage,
            total_bubbles,
            recency_bubble_offset=recency_bubble_offset,
        ),
    ]
    visible = [part for part in parts if part]
    if not visible:
        return ""
    return f" {' '.join(visible)}"


def style_activity_suffix(
    file_usage: FileContextUsage,
    total_bubbles: int = 0,
    *,
    color: bool = False,
    recency_bubble_offset: int = 0,
) -> str:
    read_suffix = format_read_activity_suffix(
        file_usage,
        total_bubbles,
        recency_bubble_offset=recency_bubble_offset,
    )
    edit_suffix = format_edit_activity_suffix(
        file_usage,
        total_bubbles,
        recency_bubble_offset=recency_bubble_offset,
    )
    if color:
        if read_suffix:
            read_suffix = ansi("33", read_suffix)
        if edit_suffix:
            edit_suffix = ansi(_ANSI_ORANGE, edit_suffix)
    visible = [part for part in (read_suffix, edit_suffix) if part]
    if not visible:
        return ""
    return f" {' '.join(visible)}"


def format_file_detail(
    file_usage: FileContextUsage,
    max_parts: int = _MAX_LINE_RANGE_PARTS,
) -> str:
    if file_usage.full_file:
        return "✓"

    parts_and_counts = list(iter_line_range_parts(file_usage.lines))
    if not parts_and_counts:
        if file_usage.deleted:
            return "deleted"
        if file_usage.edit_hits > 0:
            return "edited"
        return ""

    if len(parts_and_counts) <= max_parts:
        return ", ".join(part for part, _ in parts_and_counts)

    shown = parts_and_counts[:max_parts]
    extra_lines = sum(count for _, count in parts_and_counts[max_parts:])
    shown_text = ", ".join(part for part, _ in shown)
    return f"{shown_text}, … (+{extra_lines} lines)"
