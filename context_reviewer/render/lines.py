"""Line range formatting for context tree output."""

from __future__ import annotations

from typing import Iterable, Set, Tuple


def iter_line_range_parts(lines: Set[int]) -> Iterable[Tuple[str, int]]:
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


def format_line_ranges(lines: Set[int]) -> str:
    parts = [part for part, _ in iter_line_range_parts(lines)]
    return ", ".join(parts)
