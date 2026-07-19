
"""
Aggregate and format files/lines touched by context-gathering and edit tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Union, Iterable

_MAX_LINE_RANGE_PARTS = 8
_RECENCY_DOT_SLOTS = 5
_ANSI_RESET = "\033[0m"
_ANSI_GREEN = "92"
_ANSI_ORANGE = "38;5;208"

@dataclass
class FileContextUsage:
    lines: Set[int] = field(default_factory=set)
    full_file: bool = False
    hits: int = 0
    last_bubble_index: Optional[int] = None
    edit_hits: int = 0
    last_edit_bubble_index: Optional[int] = None
    deleted: bool = False


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


def last_user_bubble_index(messages: List[Dict]) -> Optional[int]:
    """Return the index of the last user message (type 1), or None."""
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("type") == 1:
            return index
    return None


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

@dataclass
class _ContextTreeNode:
    subdirs: Dict[str, "_ContextTreeNode"] = field(default_factory=dict)
    files: Dict[str, FileContextUsage] = field(default_factory=dict)


def _iter_line_range_parts(lines: Set[int]) -> Iterable[Tuple[str, int]]:
    if not lines:
        return

    sorted_lines = sorted(lines)
    range_start = sorted_lines[0]
    range_end = sorted_lines[0]

    def emit_range(start: int, end: int) -> Tuple[str, int]:
        if start == end:
            return f"L{start}", 1
        return f"L{start}-L{end}", end - start + 1

    for line in sorted_lines[1:]:
        if line == range_end + 1:
            range_end = line
            continue
        yield emit_range(range_start, range_end)
        range_start = line
        range_end = line

    yield emit_range(range_start, range_end)


def _format_line_ranges(lines: Set[int]) -> str:
    parts = [part for part, _ in _iter_line_range_parts(lines)]
    return ", ".join(parts)


def _format_read_activity_suffix(
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


def _format_edit_activity_suffix(
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


def _format_activity_suffix(
    file_usage: FileContextUsage,
    total_bubbles: int = 0,
    *,
    recency_bubble_offset: int = 0,
) -> str:
    """Format read/edit counts and recency in order: read, read dots, edit, edit dots."""
    parts = [
        _format_read_activity_suffix(
            file_usage,
            total_bubbles,
            recency_bubble_offset=recency_bubble_offset,
        ),
        _format_edit_activity_suffix(
            file_usage,
            total_bubbles,
            recency_bubble_offset=recency_bubble_offset,
        ),
    ]
    visible = [part for part in parts if part]
    if not visible:
        return ""
    return f" {' '.join(visible)}"


def _style_activity_suffix(
    file_usage: FileContextUsage,
    total_bubbles: int = 0,
    *,
    color: bool = False,
    recency_bubble_offset: int = 0,
) -> str:
    read_suffix = _format_read_activity_suffix(
        file_usage,
        total_bubbles,
        recency_bubble_offset=recency_bubble_offset,
    )
    edit_suffix = _format_edit_activity_suffix(
        file_usage,
        total_bubbles,
        recency_bubble_offset=recency_bubble_offset,
    )
    if color:
        if read_suffix:
            read_suffix = _ansi("33", read_suffix)
        if edit_suffix:
            edit_suffix = _ansi(_ANSI_ORANGE, edit_suffix)
    visible = [part for part in (read_suffix, edit_suffix) if part]
    if not visible:
        return ""
    return f" {' '.join(visible)}"


def _format_file_detail(
    file_usage: FileContextUsage,
    max_parts: int = _MAX_LINE_RANGE_PARTS,
) -> str:
    if file_usage.full_file:
        return "✓"

    parts_and_counts = list(_iter_line_range_parts(file_usage.lines))
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


def _build_path_tree(usage: Dict[str, FileContextUsage]) -> _ContextTreeNode:
    root = _ContextTreeNode()
    for file_path, file_usage in usage.items():
        parts = file_path.split("/")
        node = root
        for part in parts[:-1]:
            node = node.subdirs.setdefault(part, _ContextTreeNode())
        node.files[parts[-1]] = file_usage
    return root


def _ansi(code: str, text: str) -> str:
    return f"\033[{code}m{text}{_ANSI_RESET}"


def _style_tree_prefix(prefix: str, *, color: bool) -> str:
    if not color:
        return prefix

    styled = ""
    index = 0
    while index < len(prefix):
        if prefix.startswith("│   ", index):
            styled += _ansi("2", "│   ")
            index += 4
        elif prefix.startswith("├── ", index):
            styled += _ansi("2", "├── ")
            index += 4
        elif prefix.startswith("└── ", index):
            styled += _ansi("2", "└── ")
            index += 4
        else:
            styled += prefix[index]
            index += 1
    return styled


def _tree_prefix(is_last: bool, ancestors_last: List[bool]) -> str:
    prefix = ""
    for ancestor_last in ancestors_last:
        prefix += "    " if ancestor_last else "│   "
    prefix += "└── " if is_last else "├── "
    return prefix


def _format_truncation_hint(hidden_count: int, *, color: bool = False) -> str:
    label = "item" if hidden_count == 1 else "items"
    hint = f" … ({hidden_count} {label})"
    if color:
        return _ansi("2", hint)
    return hint


def _count_renderable_subtree(
    node: _ContextTreeNode,
    *,
    files_only: bool = False,
) -> int:
    count = 0
    for name in sorted(set(node.subdirs) | set(node.files)):
        if name in node.subdirs:
            count += 1
            count += _count_renderable_subtree(
                node.subdirs[name],
                files_only=files_only,
            )
        if name in node.files:
            file_usage = node.files[name]
            if files_only or _format_file_detail(file_usage):
                count += 1
    return count


def _format_tree_entry(
    prefix: str,
    name: str,
    *,
    is_dir: bool,
    activity_suffix: str = "",
    detail: str = "",
    truncation_hint: str = "",
    color: bool = False,
) -> str:
    prefix = _style_tree_prefix(prefix, color=color)
    if color:
        if is_dir:
            name = _ansi("36", f"{name}/")
        else:
            name = _ansi("1", name)
            if detail == "✓":
                detail = _ansi(_ANSI_GREEN, detail)
            elif detail == "edited":
                detail = _ansi(_ANSI_ORANGE, detail)
            elif detail == "deleted":
                detail = _ansi("35", detail)
            elif detail:
                detail = _ansi(_ANSI_GREEN, detail)
    elif is_dir:
        name = f"{name}/"

    if is_dir:
        return f"{prefix}{name}{truncation_hint}"
    if detail:
        return f"{prefix}{name}{activity_suffix} — {detail}"
    return f"{prefix}{name}{activity_suffix}"


def _render_context_tree(
    node: _ContextTreeNode,
    ancestors_last: List[bool],
    lines: List[str],
    *,
    files_only: bool = False,
    total_bubbles: int = 0,
    recency_bubble_offset: int = 0,
    color: bool = False,
    depth: int = 1,
    max_depth: Optional[int] = None,
) -> None:
    entries: List[Tuple[str, Union[_ContextTreeNode, FileContextUsage]]] = []
    for name in sorted(set(node.subdirs) | set(node.files)):
        if name in node.subdirs:
            entries.append((name, node.subdirs[name]))
        if name in node.files:
            entries.append((name, node.files[name]))

    for index, (name, value) in enumerate(entries):
        is_last = index == len(entries) - 1
        prefix = _tree_prefix(is_last, ancestors_last)
        if isinstance(value, _ContextTreeNode):
            truncation_hint = ""
            if max_depth is not None and depth >= max_depth:
                hidden_count = _count_renderable_subtree(value, files_only=files_only)
                if hidden_count > 0:
                    truncation_hint = _format_truncation_hint(
                        hidden_count,
                        color=color,
                    )
                lines.append(
                    _format_tree_entry(
                        prefix,
                        name,
                        is_dir=True,
                        truncation_hint=truncation_hint,
                        color=color,
                    )
                )
                continue

            lines.append(
                _format_tree_entry(prefix, name, is_dir=True, color=color)
            )
            _render_context_tree(
                value,
                ancestors_last + [is_last],
                lines,
                files_only=files_only,
                total_bubbles=total_bubbles,
                recency_bubble_offset=recency_bubble_offset,
                color=color,
                depth=depth + 1,
                max_depth=max_depth,
            )
            continue

        activity_suffix = _style_activity_suffix(
            value,
            total_bubbles,
            color=color,
            recency_bubble_offset=recency_bubble_offset,
        )
        if files_only:
            lines.append(
                _format_tree_entry(
                    prefix,
                    name,
                    is_dir=False,
                    activity_suffix=activity_suffix,
                    color=color,
                )
            )
            continue

        detail = _format_file_detail(value)
        if not detail:
            continue
        lines.append(
            _format_tree_entry(
                prefix,
                name,
                is_dir=False,
                activity_suffix=activity_suffix,
                detail=detail,
                color=color,
            )
        )


_NO_USER_MESSAGES = "(no user messages in dialog)"
_NO_AGENT_MESSAGES = "(no agent messages after last user message)"


@dataclass
class ContextTreeResult:
    usage: Dict[str, FileContextUsage]
    total_bubbles: int
    recency_bubble_offset: int = 0
    empty_message: Optional[str] = None


def build_context_tree(
    messages: List[Dict],
    project_root: Optional[str] = None,
    *,
    last_turn: bool = False,
) -> ContextTreeResult:
    """Collect context usage, optionally limited to the current agent turn."""
    from context_reviewer.extractor import collect_context_usage

    if not last_turn:
        return ContextTreeResult(
            collect_context_usage(messages, project_root),
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
        ),
        post_cutoff_bubbles,
        recency_bubble_offset=cutoff + 1,
    )


build_context_worktree = build_context_tree


def format_context_tree(
    usage: Dict[str, FileContextUsage],
    root_label: str = "root",
    *,
    files_only: bool = False,
    total_bubbles: int = 0,
    recency_bubble_offset: int = 0,
    empty_message: Optional[str] = None,
    color: bool = False,
    max_depth: Optional[int] = None,
) -> str:
    lines = [_ansi("1", root_label) if color else root_label]
    if empty_message:
        empty_suffix = f"└── {empty_message}"
    else:
        empty_suffix = "└── (no context files)"
    if color:
        empty_suffix = _ansi("2", empty_suffix)

    if not usage:
        lines.append(empty_suffix)
        return "\n".join(lines)

    tree = _build_path_tree(usage)
    rendered: List[str] = []
    _render_context_tree(
        tree,
        [],
        rendered,
        files_only=files_only,
        total_bubbles=total_bubbles,
        recency_bubble_offset=recency_bubble_offset,
        color=color,
        max_depth=max_depth,
    )

    if not rendered:
        lines.append(empty_suffix)
    else:
        lines.extend(rendered)

    return "\n".join(lines)

format_context_worktree = format_context_tree
