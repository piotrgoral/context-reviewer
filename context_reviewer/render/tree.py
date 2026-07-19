"""Context tree rendering for terminal output."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

from context_reviewer.context.models import FileContextUsage
from context_reviewer.render.activity import format_file_detail, style_activity_suffix
from context_reviewer.render.terminal import ansi, style_tree_prefix

_ANSI_GREEN = "92"
_ANSI_ORANGE = "38;5;208"


@dataclass
class _ContextTreeNode:
    subdirs: Dict[str, "_ContextTreeNode"] = field(default_factory=dict)
    files: Dict[str, FileContextUsage] = field(default_factory=dict)


def _build_path_tree(usage: Dict[str, FileContextUsage]) -> _ContextTreeNode:
    root = _ContextTreeNode()
    for file_path, file_usage in usage.items():
        parts = file_path.split("/")
        node = root
        for part in parts[:-1]:
            node = node.subdirs.setdefault(part, _ContextTreeNode())
        node.files[parts[-1]] = file_usage
    return root


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
        return ansi("2", hint)
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
            if files_only or format_file_detail(file_usage):
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
    prefix = style_tree_prefix(prefix, color=color)
    if color:
        if is_dir:
            name = ansi("36", f"{name}/")
        else:
            name = ansi("1", name)
            if detail == "✓":
                detail = ansi(_ANSI_GREEN, detail)
            elif detail == "edited":
                detail = ansi(_ANSI_ORANGE, detail)
            elif detail == "deleted":
                detail = ansi("35", detail)
            elif detail:
                detail = ansi(_ANSI_GREEN, detail)
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

        activity_suffix = style_activity_suffix(
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

        detail = format_file_detail(value)
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
    lines = [ansi("1", root_label) if color else root_label]
    if empty_message:
        empty_suffix = f"└── {empty_message}"
    else:
        empty_suffix = "└── (no context files)"
    if color:
        empty_suffix = ansi("2", empty_suffix)

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
