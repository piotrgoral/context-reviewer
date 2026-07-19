"""Terminal ANSI styling helpers."""

from __future__ import annotations

_ANSI_RESET = "\033[0m"


def ansi(code: str, text: str) -> str:
    return f"\033[{code}m{text}{_ANSI_RESET}"


def style_tree_prefix(prefix: str, *, color: bool) -> str:
    if not color:
        return prefix

    styled = ""
    index = 0
    while index < len(prefix):
        if prefix.startswith("│   ", index):
            styled += ansi("2", "│   ")
            index += 4
        elif prefix.startswith("├── ", index):
            styled += ansi("2", "├── ")
            index += 4
        elif prefix.startswith("└── ", index):
            styled += ansi("2", "└── ")
            index += 4
        else:
            styled += prefix[index]
            index += 1
    return styled
