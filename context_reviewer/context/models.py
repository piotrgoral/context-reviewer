"""Domain models for aggregated file context usage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Set


@dataclass
class FileContextUsage:
    lines: Set[int] = field(default_factory=set)
    full_file: bool = False
    hits: int = 0
    last_bubble_index: Optional[int] = None
    edit_hits: int = 0
    last_edit_bubble_index: Optional[int] = None
    deleted: bool = False


@dataclass
class ContextTreeResult:
    usage: Dict[str, FileContextUsage]
    total_bubbles: int
    recency_bubble_offset: int = 0
    empty_message: Optional[str] = None
