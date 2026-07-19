"""Read/edit activity suffixes and file detail formatting."""

from __future__ import annotations

from typing import Literal, Set

from context_reviewer.context.models import FileContextUsage
from context_reviewer.render.lines import iter_line_range_parts
from context_reviewer.render.recency import format_recency_dots, normalize_bubble_percent
from context_reviewer.render.terminal import ansi

_MAX_LINE_RANGE_PARTS = 8
ContextTreeMode = Literal["reads", "edits"]
_ANSI_GREEN_READ = "92"
_ANSI_ORANGE = "38;5;208"


def _total_read_hits(file_usage: FileContextUsage) -> int:
    if file_usage.hits > 0:
        return file_usage.hits
    return (
        file_usage.read_hits
        + file_usage.search_hits
        + file_usage.code_search_hits
    )


def _read_lines(file_usage: FileContextUsage) -> Set[int]:
    lines = (
        set(file_usage.read_lines)
        | set(file_usage.search_lines)
        | set(file_usage.code_search_lines)
    )
    if lines:
        return lines
    return set(file_usage.lines)


def _format_line_range_detail(
    lines: Set[int],
    *,
    max_parts: int = _MAX_LINE_RANGE_PARTS,
) -> str:
    parts_and_counts = list(iter_line_range_parts(lines))
    if not parts_and_counts:
        return ""

    if len(parts_and_counts) <= max_parts:
        return ", ".join(part for part, _ in parts_and_counts)

    shown = parts_and_counts[:max_parts]
    extra_lines = sum(count for _, count in parts_and_counts[max_parts:])
    shown_text = ", ".join(part for part, _ in shown)
    return f"{shown_text}, … (+{extra_lines} lines)"


def format_read_activity_suffix(
    file_usage: FileContextUsage,
    total_bubbles: int = 0,
    *,
    recency_bubble_offset: int = 0,
) -> str:
    hits = _total_read_hits(file_usage)
    if hits <= 0:
        return ""

    parts = [f"[{hits} read]"]
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
    if file_usage.edit_hits <= 0 and not file_usage.deleted:
        return ""
    edit_label = "edit" if file_usage.edit_hits == 1 else "edits"
    count = file_usage.edit_hits if file_usage.edit_hits > 0 else 1
    parts = [f"[{count} {edit_label}]"]
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
    mode: ContextTreeMode = "reads",
    recency_bubble_offset: int = 0,
) -> str:
    if mode == "edits":
        suffix = format_edit_activity_suffix(
            file_usage,
            total_bubbles,
            recency_bubble_offset=recency_bubble_offset,
        )
    else:
        suffix = format_read_activity_suffix(
            file_usage,
            total_bubbles,
            recency_bubble_offset=recency_bubble_offset,
        )
    if not suffix:
        return ""
    return f" {suffix}"


def style_activity_suffix(
    file_usage: FileContextUsage,
    total_bubbles: int = 0,
    *,
    mode: ContextTreeMode = "reads",
    color: bool = False,
    recency_bubble_offset: int = 0,
) -> str:
    if mode == "edits":
        suffix = format_edit_activity_suffix(
            file_usage,
            total_bubbles,
            recency_bubble_offset=recency_bubble_offset,
        )
        if color and suffix:
            suffix = ansi(_ANSI_ORANGE, suffix)
    elif color:
        suffix = format_read_activity_suffix(
            file_usage,
            total_bubbles,
            recency_bubble_offset=recency_bubble_offset,
        )
        if suffix:
            hits_label, _, rest = suffix.partition("]")
            if hits_label:
                suffix = ansi(_ANSI_GREEN_READ, f"{hits_label}]") + rest
    else:
        suffix = format_read_activity_suffix(
            file_usage,
            total_bubbles,
            recency_bubble_offset=recency_bubble_offset,
        )
    if not suffix:
        return ""
    return f" {suffix}"


def format_read_file_detail(
    file_usage: FileContextUsage,
    max_parts: int = _MAX_LINE_RANGE_PARTS,
) -> str:
    return style_read_file_detail(file_usage, color=False, max_parts=max_parts)


def style_read_file_detail(
    file_usage: FileContextUsage,
    *,
    color: bool = False,
    max_parts: int = _MAX_LINE_RANGE_PARTS,
) -> str:
    if file_usage.full_file:
        detail = "✓"
        if color:
            return ansi(_ANSI_GREEN_READ, detail)
        return detail

    lines = _read_lines(file_usage)
    detail = _format_line_range_detail(lines, max_parts=max_parts)
    if not detail:
        return ""
    if color:
        return ansi(_ANSI_GREEN_READ, detail)
    return detail


def format_edit_file_detail(
    file_usage: FileContextUsage,
    max_parts: int = _MAX_LINE_RANGE_PARTS,
) -> str:
    return style_edit_file_detail(file_usage, color=False, max_parts=max_parts)


def style_edit_file_detail(
    file_usage: FileContextUsage,
    *,
    color: bool = False,
    max_parts: int = _MAX_LINE_RANGE_PARTS,
) -> str:
    if file_usage.deleted:
        detail = "deleted"
        if color:
            return ansi("35", detail)
        return detail
    if file_usage.edit_full_file:
        detail = "✓"
        if color:
            return ansi(_ANSI_ORANGE, detail)
        return detail

    detail = _format_line_range_detail(set(file_usage.edit_lines), max_parts=max_parts)
    if detail:
        if color:
            return ansi(_ANSI_ORANGE, detail)
        return detail

    if file_usage.edit_hits > 0:
        detail = "edited"
        if color:
            return ansi(_ANSI_ORANGE, detail)
        return detail
    return ""


def format_file_detail(
    file_usage: FileContextUsage,
    *,
    mode: ContextTreeMode = "reads",
    max_parts: int = _MAX_LINE_RANGE_PARTS,
) -> str:
    return style_file_detail(
        file_usage,
        mode=mode,
        color=False,
        max_parts=max_parts,
    )


def style_file_detail(
    file_usage: FileContextUsage,
    *,
    mode: ContextTreeMode = "reads",
    color: bool = False,
    max_parts: int = _MAX_LINE_RANGE_PARTS,
) -> str:
    if mode == "edits":
        return style_edit_file_detail(file_usage, color=color, max_parts=max_parts)
    return style_read_file_detail(file_usage, color=color, max_parts=max_parts)


def has_read_activity(file_usage: FileContextUsage) -> bool:
    return (
        file_usage.hits > 0
        or file_usage.full_file
        or bool(_read_lines(file_usage))
    )


def has_edit_activity(file_usage: FileContextUsage) -> bool:
    return (
        file_usage.edit_hits > 0
        or file_usage.deleted
        or file_usage.edit_full_file
        or bool(file_usage.edit_lines)
    )


def has_mode_detail(
    file_usage: FileContextUsage,
    *,
    mode: ContextTreeMode = "reads",
) -> bool:
    if mode == "edits":
        return bool(format_edit_file_detail(file_usage))
    return bool(format_read_file_detail(file_usage))
