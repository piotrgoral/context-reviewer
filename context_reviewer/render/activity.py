"""Read/edit activity suffixes and file detail formatting."""

from __future__ import annotations

from typing import List, Literal, Set, Tuple

from context_reviewer.context.models import FileContextUsage
from context_reviewer.render.lines import iter_line_range_parts
from context_reviewer.render.recency import format_recency_dots, normalize_bubble_percent
from context_reviewer.render.terminal import ansi

_MAX_LINE_RANGE_PARTS = 8
ContextReadKind = Literal["read", "search", "code_search"]
_ANSI_GREEN_READ = "92"
_ANSI_GREEN_SEARCH = "32"
_ANSI_GREEN_CODE_SEARCH = "38;5;77"
_ANSI_ORANGE = "38;5;208"

_READ_KIND_LABELS: dict[ContextReadKind, str] = {
    "read": "read",
    "search": "search",
    "code_search": "code search",
}
_READ_KIND_COLORS: dict[ContextReadKind, str] = {
    "read": _ANSI_GREEN_READ,
    "search": _ANSI_GREEN_SEARCH,
    "code_search": _ANSI_GREEN_CODE_SEARCH,
}


def _typed_read_hit_counts(
    file_usage: FileContextUsage,
) -> List[Tuple[ContextReadKind, int]]:
    typed = [
        ("read", file_usage.read_hits),
        ("search", file_usage.search_hits),
        ("code_search", file_usage.code_search_hits),
    ]
    if not any(count for _, count in typed) and file_usage.hits > 0:
        return [("read", file_usage.hits)]
    return [(kind, count) for kind, count in typed if count > 0]


def _partition_lines_by_kind(
    file_usage: FileContextUsage,
) -> List[Tuple[ContextReadKind, Set[int]]]:
    read_lines = set(file_usage.read_lines)
    search_lines = set(file_usage.search_lines) - read_lines
    code_search_lines = (
        set(file_usage.code_search_lines) - read_lines - search_lines
    )
    partitioned = [
        ("read", read_lines),
        ("search", search_lines),
        ("code_search", code_search_lines),
    ]
    if not any(lines for _, lines in partitioned) and file_usage.lines:
        return [("read", set(file_usage.lines))]
    return [(kind, lines) for kind, lines in partitioned if lines]


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
    hit_counts = _typed_read_hit_counts(file_usage)
    if not hit_counts:
        return ""

    parts = [
        f"[{count} {_READ_KIND_LABELS[kind]}]" for kind, count in hit_counts
    ]
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


def _style_read_hit_suffix(
    file_usage: FileContextUsage,
    total_bubbles: int = 0,
    *,
    recency_bubble_offset: int = 0,
) -> str:
    hit_counts = _typed_read_hit_counts(file_usage)
    if not hit_counts:
        return ""

    parts: List[str] = []
    for kind, count in hit_counts:
        label = f"[{count} {_READ_KIND_LABELS[kind]}]"
        parts.append(ansi(_READ_KIND_COLORS[kind], label))

    if file_usage.last_bubble_index is not None and total_bubbles > 1:
        bubble_percent = normalize_bubble_percent(
            file_usage.last_bubble_index,
            total_bubbles,
            bubble_offset=recency_bubble_offset,
        )
        parts.append(format_recency_dots(bubble_percent))
    return " ".join(parts)


def style_activity_suffix(
    file_usage: FileContextUsage,
    total_bubbles: int = 0,
    *,
    color: bool = False,
    recency_bubble_offset: int = 0,
) -> str:
    if color:
        read_suffix = _style_read_hit_suffix(
            file_usage,
            total_bubbles,
            recency_bubble_offset=recency_bubble_offset,
        )
    else:
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
    if color and edit_suffix:
        edit_suffix = ansi(_ANSI_ORANGE, edit_suffix)
    visible = [part for part in (read_suffix, edit_suffix) if part]
    if not visible:
        return ""
    return f" {' '.join(visible)}"


def format_file_detail(
    file_usage: FileContextUsage,
    max_parts: int = _MAX_LINE_RANGE_PARTS,
) -> str:
    return style_file_detail(file_usage, color=False, max_parts=max_parts)


def style_file_detail(
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

    partitioned = _partition_lines_by_kind(file_usage)
    if partitioned:
        rendered_parts: List[str] = []
        for kind, lines in partitioned:
            detail = _format_line_range_detail(lines, max_parts=max_parts)
            if not detail:
                continue
            if color:
                detail = ansi(_READ_KIND_COLORS[kind], detail)
            rendered_parts.append(detail)
        if rendered_parts:
            return ", ".join(rendered_parts)

    if file_usage.deleted:
        detail = "deleted"
        if color:
            return ansi("35", detail)
        return detail
    if file_usage.edit_hits > 0:
        detail = "edited"
        if color:
            return ansi(_ANSI_ORANGE, detail)
        return detail
    return ""
