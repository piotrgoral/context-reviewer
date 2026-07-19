"""Tests for context tree rendering and Cursor context extraction."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from context_reviewer.agents.cursor.context import (
    build_context_tree,
    last_user_bubble_index,
)
from context_reviewer.agents.cursor.extractor import (
    collect_context_usage,
    extract_edit_context,
    extract_read_context,
    is_context_tool,
    is_edit_tool,
)
from context_reviewer.context.models import FileContextUsage
from context_reviewer.render import format_context_tree
from context_reviewer.render.recency import (
    format_recency_dots,
    normalize_bubble_percent,
    recency_filled_dots,
)

PROJECT_ROOT = "/Users/p/project"

class TestLastUserBubbleIndex(unittest.TestCase):
    def test_finds_last_user_message(self):
        messages = [
            {"type": 1},
            {"type": 2},
            {"type": 1},
            {"type": 2},
        ]
        self.assertEqual(last_user_bubble_index(messages), 2)

    def test_no_user_messages(self):
        self.assertIsNone(last_user_bubble_index([{"type": 2}, {"type": 2}]))

class TestLastTurnContext(unittest.TestCase):
    def _read_message(self, *, limit: int, bubble_type: int = 2) -> dict:
        return {
            "type": bubble_type,
            "tool_data": {
                "name": "read_file_v2",
                "status": "completed",
                "rawArgs": {
                    "path": f"{PROJECT_ROOT}/file.py",
                    "limit": limit,
                },
                "result": {
                    "contents": "\n".join("x" for _ in range(limit)),
                    "totalLinesInFile": 50,
                },
            },
        }

    def test_last_turn_excludes_earlier_reads(self):
        messages = [
            self._read_message(limit=5),
            {"type": 1, "text": "follow up"},
            self._read_message(limit=10),
        ]
        worktree = build_context_tree(
            messages,
            project_root=PROJECT_ROOT,
            last_turn=True,
        )
        self.assertIsNone(worktree.empty_message)
        self.assertEqual(worktree.total_bubbles, 1)
        self.assertEqual(worktree.recency_bubble_offset, 2)
        self.assertEqual(worktree.usage["file.py"].hits, 1)
        self.assertEqual(set(worktree.usage["file.py"].lines), set(range(1, 11)))

    def test_last_turn_no_user_messages(self):
        messages = [self._read_message(limit=5)]
        worktree = build_context_tree(
            messages,
            project_root=PROJECT_ROOT,
            last_turn=True,
        )
        self.assertEqual(worktree.usage, {})
        self.assertEqual(worktree.empty_message, "(no user messages in dialog)")
        output = format_context_tree(
            worktree.usage,
            empty_message=worktree.empty_message,
        )
        self.assertIn("(no user messages in dialog)", output)

    def test_last_turn_no_agent_messages(self):
        messages = [
            self._read_message(limit=5),
            {"type": 1, "text": "waiting"},
        ]
        worktree = build_context_tree(
            messages,
            project_root=PROJECT_ROOT,
            last_turn=True,
        )
        self.assertEqual(worktree.usage, {})
        self.assertEqual(
            worktree.empty_message,
            "(no agent messages after last user message)",
        )

    def test_last_turn_recency_relative_to_cutoff(self):
        def read_file(path: str) -> dict:
            return {
                "type": 2,
                "tool_data": {
                    "name": "read_file_v2",
                    "status": "completed",
                    "rawArgs": {
                        "path": f"{PROJECT_ROOT}/{path}",
                        "limit": 5,
                    },
                    "result": {
                        "contents": "\n".join("x" for _ in range(5)),
                        "totalLinesInFile": 20,
                    },
                },
            }

        messages = [
            {"type": 1, "text": "start"},
            read_file("before.py"),
            {"type": 1, "text": "again"},
            read_file("early.py"),
            read_file("late.py"),
        ]
        worktree = build_context_tree(
            messages,
            project_root=PROJECT_ROOT,
            last_turn=True,
        )
        output = format_context_tree(
            worktree.usage,
            total_bubbles=worktree.total_bubbles,
            recency_bubble_offset=worktree.recency_bubble_offset,
        )
        self.assertNotIn("before.py", output)
        self.assertIn("early.py [1 read] [·        ]", output)
        self.assertIn("late.py [1 read] [· · · · ·]", output)

class TestRecencyDots(unittest.TestCase):
    def test_normalize_bubble_percent(self):
        self.assertEqual(normalize_bubble_percent(0, 10), 0)
        self.assertEqual(normalize_bubble_percent(9, 10), 100)
        self.assertEqual(normalize_bubble_percent(5, 11), 50)
        self.assertEqual(normalize_bubble_percent(0, 1), 0)

    def test_normalize_bubble_percent_with_offset(self):
        self.assertEqual(
            normalize_bubble_percent(9, 4, bubble_offset=6),
            100,
        )
        self.assertEqual(
            normalize_bubble_percent(6, 4, bubble_offset=6),
            0,
        )

    def test_recency_filled_dots_quintiles(self):
        self.assertEqual(recency_filled_dots(0), 1)
        self.assertEqual(recency_filled_dots(10), 1)
        self.assertEqual(recency_filled_dots(20), 1)
        self.assertEqual(recency_filled_dots(21), 2)
        self.assertEqual(recency_filled_dots(50), 3)
        self.assertEqual(recency_filled_dots(90), 5)
        self.assertEqual(recency_filled_dots(100), 5)

    def test_format_recency_dots_fixed_width(self):
        for percent, expected in (
            (0, "[·        ]"),
            (10, "[·        ]"),
            (50, "[· · ·    ]"),
            (100, "[· · · · ·]"),
        ):
            rendered = format_recency_dots(percent)
            self.assertEqual(rendered, expected)
            self.assertEqual(len(rendered), 11)

class TestContextToolDetection(unittest.TestCase):
    def test_is_context_tool(self):
        for name in (
            "read_file",
            "read_file_v2",
            "ripgrep_raw_search",
            "grep",
            "rg",
            "grep_search",
            "codebase_search",
            "semantic_search_full",
        ):
            self.assertTrue(is_context_tool(name))
        self.assertFalse(is_context_tool("glob_file_search"))
        self.assertFalse(is_context_tool("run_terminal_cmd"))

    def test_is_edit_tool(self):
        for name in (
            "edit_file_v2",
            "search_replace",
            "write",
            "edit_file",
            "edit_notebook",
            "apply_patch",
            "MultiEdit",
            "delete_file",
        ):
            self.assertTrue(is_edit_tool(name))
        self.assertFalse(is_edit_tool("read_file_v2"))

class TestExtractReadContext(unittest.TestCase):
    def test_partial_read_with_limit(self):
        tool_data = {
            "name": "read_file_v2",
            "status": "completed",
            "rawArgs": {
                "path": f"{PROJECT_ROOT}/pyproject.toml",
                "limit": 30,
            },
            "result": {
                "contents": "\n".join(f"line {i}" for i in range(1, 31)),
                "totalLinesInFile": 114,
            },
        }
        result = extract_read_context(tool_data)
        self.assertIsNotNone(result)
        file_path, usage = result
        self.assertEqual(file_path, f"{PROJECT_ROOT}/pyproject.toml")
        self.assertFalse(usage.full_file)
        self.assertEqual(usage.lines, set(range(1, 31)))

    def test_full_file_flag(self):
        tool_data = {
            "name": "read_file",
            "status": "completed",
            "rawArgs": {
                "path": f"{PROJECT_ROOT}/README.md",
                "readEntireFile": True,
            },
            "result": {"totalLinesInFile": 800},
        }
        _, usage = extract_read_context(tool_data)
        self.assertTrue(usage.full_file)
        self.assertEqual(usage.lines, set())

    def test_full_file_when_range_covers_total(self):
        tool_data = {
            "name": "read_file_v2",
            "status": "completed",
            "rawArgs": {
                "path": f"{PROJECT_ROOT}/small.py",
                "limit": 50,
            },
            "result": {
                "contents": "a\nb\nc",
                "totalLinesInFile": 3,
            },
        }
        _, usage = extract_read_context(tool_data)
        self.assertTrue(usage.full_file)

    def test_metadata_only_full_read_empty_contents(self):
        tool_data = {
            "name": "read_file_v2",
            "status": "completed",
            "rawArgs": {
                "path": f"{PROJECT_ROOT}/cursor_chronicle/tool_results.py",
            },
            "params": {
                "targetFile": f"{PROJECT_ROOT}/cursor_chronicle/tool_results.py",
                "charsLimit": 1000000,
            },
            "result": {
                "contents": "",
                "totalLinesInFile": 531,
            },
        }
        _, usage = extract_read_context(tool_data)
        self.assertTrue(usage.full_file)

    def test_result_line_range(self):
        tool_data = {
            "name": "read_file",
            "status": "completed",
            "rawArgs": {"path": f"{PROJECT_ROOT}/module.py"},
            "result": {
                "startLineOneIndexed": 10,
                "endLineOneIndexedInclusive": 25,
                "totalLinesInFile": 100,
                "contents": "\n".join("x" for _ in range(16)),
            },
        }
        _, usage = extract_read_context(tool_data)
        self.assertFalse(usage.full_file)
        self.assertEqual(usage.lines, set(range(10, 26)))

    def test_content_lines_preferred_over_limit(self):
        tool_data = {
            "name": "read_file_v2",
            "status": "completed",
            "rawArgs": {
                "path": f"{PROJECT_ROOT}/module.py",
                "limit": 50,
            },
            "result": {
                "contents": "\n".join("x" for _ in range(20)),
                "totalLinesInFile": 100,
            },
        }
        _, usage = extract_read_context(tool_data)
        self.assertEqual(usage.lines, set(range(1, 21)))

class TestCollectContextUsage(unittest.TestCase):
    def _example_dialog_messages(self):
        readme_matches = [
            {"lineNumber": line, "content": f"content line {line}"}
            for line in (35, 36, 498, 646, 647, 727, 770)
        ]
        return [
            {
                "type": 2,
                "tool_data": {
                    "name": "glob_file_search",
                    "status": "completed",
                    "rawArgs": {
                        "globPattern": "**/README*",
                        "targetDirectory": PROJECT_ROOT,
                    },
                },
            },
            {
                "type": 2,
                "tool_data": {
                    "name": "read_file_v2",
                    "status": "completed",
                    "rawArgs": {
                        "path": f"{PROJECT_ROOT}/pyproject.toml",
                        "limit": 30,
                    },
                    "result": {
                        "contents": "\n".join(f"line {i}" for i in range(1, 31)),
                        "totalLinesInFile": 114,
                    },
                },
            },
            {
                "type": 2,
                "tool_data": {
                    "name": "ripgrep_raw_search",
                    "status": "completed",
                    "rawArgs": {
                        "pattern": "python|conda|venv",
                        "path": f"{PROJECT_ROOT}/README.md",
                    },
                    "result": {
                        "success": {
                            "workspaceResults": {
                                "/workspace": {
                                    "content": {
                                        "matches": [
                                            {
                                                "file": "README.md",
                                                "matches": readme_matches,
                                            }
                                        ]
                                    }
                                }
                            }
                        }
                    },
                },
            },
        ]

    def test_example_dialog(self):
        messages = self._example_dialog_messages()
        usage = collect_context_usage(messages, project_root=PROJECT_ROOT)
        output = format_context_tree(usage, total_bubbles=len(messages))
        self.assertIn("pyproject.toml [1 read] [· · ·    ] — L1-L30", output)
        self.assertIn("README.md [1 search] [· · · · ·] —", output)
        for line in (35, 36, 498, 646, 647, 727, 770):
            self.assertIn(f"L{line}", output)
        self.assertNotIn("glob_file_search", output)

    def test_merge_reads_same_file(self):
        messages = [
            {
                "type": 2,
                "tool_data": {
                    "name": "read_file_v2",
                    "status": "completed",
                    "rawArgs": {
                        "path": f"{PROJECT_ROOT}/module.py",
                        "offset": 1,
                        "limit": 10,
                    },
                    "result": {
                        "contents": "\n".join("x" for _ in range(10)),
                        "totalLinesInFile": 100,
                    },
                },
            },
            {
                "type": 2,
                "tool_data": {
                    "name": "read_file_v2",
                    "status": "completed",
                    "rawArgs": {
                        "path": f"{PROJECT_ROOT}/module.py",
                        "offset": 20,
                        "limit": 5,
                    },
                    "result": {
                        "contents": "\n".join("y" for _ in range(5)),
                        "totalLinesInFile": 100,
                    },
                },
            },
        ]
        usage = collect_context_usage(messages, project_root=PROJECT_ROOT)
        self.assertEqual(usage["module.py"].lines, set(range(1, 11)) | set(range(20, 25)))
        self.assertEqual(usage["module.py"].last_bubble_index, 1)
        self.assertEqual(usage["module.py"].hits, 2)
        self.assertEqual(usage["module.py"].read_hits, 2)

    def test_full_file_overrides_partial(self):
        messages = [
            {
                "type": 2,
                "tool_data": {
                    "name": "read_file",
                    "status": "completed",
                    "rawArgs": {
                        "path": f"{PROJECT_ROOT}/file.py",
                        "limit": 10,
                    },
                    "result": {
                        "contents": "\n".join("x" for _ in range(10)),
                        "totalLinesInFile": 50,
                    },
                },
            },
            {
                "type": 2,
                "tool_data": {
                    "name": "read_file",
                    "status": "completed",
                    "rawArgs": {
                        "path": f"{PROJECT_ROOT}/file.py",
                        "readEntireFile": True,
                    },
                    "result": {"totalLinesInFile": 50},
                },
            },
        ]
        usage = collect_context_usage(messages, project_root=PROJECT_ROOT)
        self.assertTrue(usage["file.py"].full_file)

    def test_metadata_full_read_unions_with_partial_read(self):
        messages = [
            {
                "type": 2,
                "tool_data": {
                    "name": "read_file_v2",
                    "status": "completed",
                    "rawArgs": {
                        "path": f"{PROJECT_ROOT}/cursor_chronicle/tool_results.py",
                    },
                    "result": {
                        "contents": "",
                        "totalLinesInFile": 531,
                    },
                },
            },
            {
                "type": 2,
                "tool_data": {
                    "name": "read_file_v2",
                    "status": "completed",
                    "rawArgs": {
                        "path": f"{PROJECT_ROOT}/cursor_chronicle/tool_results.py",
                        "limit": 20,
                    },
                    "result": {
                        "contents": "\n".join("x" for _ in range(20)),
                        "totalLinesInFile": 531,
                    },
                },
            },
        ]
        usage = collect_context_usage(messages, project_root=PROJECT_ROOT)
        self.assertTrue(usage["cursor_chronicle/tool_results.py"].full_file)
        self.assertEqual(usage["cursor_chronicle/tool_results.py"].hits, 2)
        self.assertEqual(usage["cursor_chronicle/tool_results.py"].last_bubble_index, 1)
        output = format_context_tree(usage, total_bubbles=len(messages))
        self.assertIn("tool_results.py [2 read] [· · · · ·] — ✓", output)

    def test_excludes_paths_outside_project(self):
        messages = [
            {
                "type": 2,
                "tool_data": {
                    "name": "read_file_v2",
                    "status": "completed",
                    "rawArgs": {
                        "path": "/Users/p/.cursor/projects/terminals/1.txt",
                        "limit": 3,
                    },
                    "result": {
                        "contents": "a\nb\nc",
                        "totalLinesInFile": 10,
                    },
                },
            },
        ]
        usage = collect_context_usage(messages, project_root=PROJECT_ROOT)
        self.assertEqual(usage, {})

    def test_path_normalization(self):
        messages = [
            {
                "type": 2,
                "tool_data": {
                    "name": "read_file_v2",
                    "status": "completed",
                    "rawArgs": {
                        "path": f"{PROJECT_ROOT}/src/app.py",
                        "limit": 5,
                    },
                    "result": {
                        "contents": "\n".join("x" for _ in range(5)),
                        "totalLinesInFile": 20,
                    },
                },
            },
        ]
        usage = collect_context_usage(messages, project_root=PROJECT_ROOT)
        self.assertIn("src/app.py", usage)

    def test_codebase_search(self):
        messages = [
            {
                "type": 2,
                "tool_data": {
                    "name": "codebase_search",
                    "status": "completed",
                    "result": {
                        "codeResults": [
                            {
                                "codeBlock": {
                                    "relativeWorkspacePath": "src/handler.py",
                                    "detailedLines": [
                                        {"lineNumber": 10, "text": "class Handler:"},
                                        {"lineNumber": 12, "text": "    def run(self):"},
                                    ],
                                }
                            }
                        ]
                    },
                },
            },
        ]
        usage = collect_context_usage(messages, project_root=PROJECT_ROOT)
        self.assertEqual(usage["src/handler.py"].lines, {10, 12})
        self.assertEqual(usage["src/handler.py"].code_search_hits, 1)
        self.assertEqual(usage["src/handler.py"].read_hits, 0)

    def test_skips_non_completed_tools(self):
        messages = [
            {
                "type": 2,
                "tool_data": {
                    "name": "read_file_v2",
                    "status": "running",
                    "rawArgs": {"path": f"{PROJECT_ROOT}/skip.py", "limit": 5},
                },
            },
        ]
        usage = collect_context_usage(messages, project_root=PROJECT_ROOT)
        self.assertEqual(usage, {})

class TestExtractEditContext(unittest.TestCase):
    def test_search_replace_applied(self):
        tool_data = {
            "name": "search_replace",
            "status": "completed",
            "rawArgs": {
                "file_path": f"{PROJECT_ROOT}/cursor_chronicle/cli.py",
            },
            "result": {"isApplied": True},
        }
        result = extract_edit_context(tool_data)
        self.assertEqual(
            result,
            (f"{PROJECT_ROOT}/cursor_chronicle/cli.py", False),
        )

    def test_skips_rejected_write(self):
        tool_data = {
            "name": "write",
            "status": "completed",
            "rawArgs": {"file_path": f"{PROJECT_ROOT}/new.py"},
            "result": {"rejected": True},
        }
        self.assertIsNone(extract_edit_context(tool_data))

    def test_edit_file_v2_without_is_applied(self):
        tool_data = {
            "name": "edit_file_v2",
            "status": "completed",
            "rawArgs": {"path": f"{PROJECT_ROOT}/module.py"},
            "result": {"afterContentId": "abc"},
        }
        result = extract_edit_context(tool_data)
        self.assertEqual(result, (f"{PROJECT_ROOT}/module.py", False))

    def test_delete_file(self):
        tool_data = {
            "name": "delete_file",
            "status": "completed",
            "rawArgs": {"path": f"{PROJECT_ROOT}/old.py"},
            "result": {"fileDeletedSuccessfully": True},
        }
        result = extract_edit_context(tool_data)
        self.assertEqual(result, (f"{PROJECT_ROOT}/old.py", True))

class TestCollectEditUsage(unittest.TestCase):
    def test_collects_edits_and_reads_on_same_file(self):
        messages = [
            {
                "type": 2,
                "tool_data": {
                    "name": "read_file_v2",
                    "status": "completed",
                    "rawArgs": {
                        "path": f"{PROJECT_ROOT}/cli.py",
                        "limit": 10,
                    },
                    "result": {
                        "contents": "\n".join("x" for _ in range(10)),
                        "totalLinesInFile": 100,
                    },
                },
            },
            {
                "type": 2,
                "tool_data": {
                    "name": "search_replace",
                    "status": "completed",
                    "rawArgs": {"file_path": f"{PROJECT_ROOT}/cli.py"},
                    "result": {"isApplied": True},
                },
            },
            {
                "type": 2,
                "tool_data": {
                    "name": "search_replace",
                    "status": "completed",
                    "rawArgs": {"file_path": f"{PROJECT_ROOT}/cli.py"},
                    "result": {"isApplied": True},
                },
            },
            {
                "type": 2,
                "tool_data": {
                    "name": "search_replace",
                    "status": "completed",
                    "rawArgs": {"file_path": f"{PROJECT_ROOT}/cli.py"},
                    "result": {"isApplied": True},
                },
            },
        ]
        usage = collect_context_usage(messages, project_root=PROJECT_ROOT)
        self.assertEqual(usage["cli.py"].hits, 1)
        self.assertEqual(usage["cli.py"].edit_hits, 3)
        self.assertEqual(usage["cli.py"].last_bubble_index, 0)
        self.assertEqual(usage["cli.py"].last_edit_bubble_index, 3)

        output = format_context_tree(usage, total_bubbles=len(messages))
        self.assertIn(
            "cli.py [1 read] [·        ] [3 edits] [· · · · ·] — L1-L10",
            output,
        )

    def test_edit_only_file_appears_in_tree(self):
        messages = [
            {
                "type": 2,
                "tool_data": {
                    "name": "write",
                    "status": "completed",
                    "rawArgs": {"file_path": f"{PROJECT_ROOT}/new.py"},
                    "result": {"rejected": False},
                },
            },
        ]
        usage = collect_context_usage(messages, project_root=PROJECT_ROOT)
        output = format_context_tree(usage, total_bubbles=5)
        self.assertIn("new.py [1 edit] [·        ] — edited", output)

    def test_skips_failed_edits(self):
        messages = [
            {
                "type": 2,
                "tool_data": {
                    "name": "search_replace",
                    "status": "completed",
                    "rawArgs": {"file_path": f"{PROJECT_ROOT}/skip.py"},
                    "result": {"isApplied": False},
                },
            },
        ]
        usage = collect_context_usage(messages, project_root=PROJECT_ROOT)
        self.assertEqual(usage, {})

class TestFormatContextWorktree(unittest.TestCase):
    def test_empty_usage(self):
        self.assertEqual(
            format_context_tree({}),
            "root\n└── (no context files)",
        )

    def test_full_file_shows_checkmark(self):

        output = format_context_tree(
            {"README.md": FileContextUsage(full_file=True)}
        )
        self.assertIn("README.md — ✓", output)

    def test_root_label(self):

        output = format_context_tree(
            {"a.py": FileContextUsage(lines={1})},
            root_label="workspace",
        )
        self.assertTrue(output.startswith("workspace"))

    def test_tree_shows_recency_when_total_bubbles_provided(self):

        output = format_context_tree(
            {
                "early.py": FileContextUsage(
                    lines={1},
                    hits=1,
                    last_bubble_index=0,
                ),
                "late.py": FileContextUsage(
                    full_file=True,
                    hits=1,
                    last_bubble_index=9,
                ),
            },
            total_bubbles=10,
        )
        self.assertIn("early.py [1 read] [·        ] — L1", output)
        self.assertIn("late.py [1 read] [· · · · ·] — ✓", output)

    def test_tree_shows_read_and_edit_activity(self):

        output = format_context_tree(
            {
                "cli.py": FileContextUsage(
                    lines=set(range(1, 11)),
                    hits=6,
                    last_bubble_index=2,
                    edit_hits=3,
                    last_edit_bubble_index=8,
                ),
            },
            total_bubbles=10,
        )
        self.assertIn(
            "cli.py [6 read] [· ·      ] [3 edits] [· · · · ·] — L1-L10",
            output,
        )

    def test_tree_glyphs_and_nesting(self):

        output = format_context_tree(
            {
                "README.md": FileContextUsage(lines={1, 2}),
                "cursor_chronicle/cli.py": FileContextUsage(full_file=True),
                "tests/test_cli.py": FileContextUsage(lines={10}),
            }
        )
        self.assertEqual(
            output,
            "\n".join(
                [
                    "root",
                    "├── README.md — L1-L2",
                    "├── cursor_chronicle/",
                    "│   └── cli.py — ✓",
                    "└── tests/",
                    "    └── test_cli.py — L10",
                ]
            ),
        )

    def test_tree_depth_limits_top_level(self):

        output = format_context_tree(
            {
                "README.md": FileContextUsage(lines={1, 2}),
                "cursor_chronicle/cli.py": FileContextUsage(full_file=True),
                "tests/test_cli.py": FileContextUsage(lines={10}),
            },
            max_depth=1,
        )
        self.assertEqual(
            output,
            "\n".join(
                [
                    "root",
                    "├── README.md — L1-L2",
                    "├── cursor_chronicle/ … (1 item)",
                    "└── tests/ … (1 item)",
                ]
            ),
        )

    def test_tree_depth_shows_intermediate_levels(self):

        output = format_context_tree(
            {
                "README.md": FileContextUsage(lines={1, 2}),
                "cursor_chronicle/cli.py": FileContextUsage(full_file=True),
                "cursor_chronicle/pkg/deep.py": FileContextUsage(lines={5}),
                "tests/test_cli.py": FileContextUsage(lines={10}),
            },
            max_depth=2,
        )
        self.assertEqual(
            output,
            "\n".join(
                [
                    "root",
                    "├── README.md — L1-L2",
                    "├── cursor_chronicle/",
                    "│   ├── cli.py — ✓",
                    "│   └── pkg/ … (1 item)",
                    "└── tests/",
                    "    └── test_cli.py — L10",
                ]
            ),
        )

    def test_tree_depth_respects_files_only(self):

        output = format_context_tree(
            {
                "README.md": FileContextUsage(lines={1, 2}),
                "cursor_chronicle/cli.py": FileContextUsage(full_file=True),
                "tests/test_cli.py": FileContextUsage(lines={10}),
            },
            files_only=True,
            max_depth=1,
        )
        self.assertEqual(
            output,
            "\n".join(
                [
                    "root",
                    "├── README.md",
                    "├── cursor_chronicle/ … (1 item)",
                    "└── tests/ … (1 item)",
                ]
            ),
        )

    def test_truncates_long_line_lists(self):

        lines = {line for line in range(1, 201, 2)}
        output = format_context_tree(
            {"big.py": FileContextUsage(lines=lines)},
            root_label="root",
        )
        self.assertIn("… (+", output)
        self.assertIn("lines)", output)
        self.assertNotIn("L199", output)

    def test_files_only_omits_line_details(self):

        output = format_context_tree(
            {
                "README.md": FileContextUsage(lines={1, 2}),
                "cursor_chronicle/cli.py": FileContextUsage(full_file=True),
                "tests/test_cli.py": FileContextUsage(lines={10}),
            },
            files_only=True,
        )
        self.assertEqual(
            output,
            "\n".join(
                [
                    "root",
                    "├── README.md",
                    "├── cursor_chronicle/",
                    "│   └── cli.py",
                    "└── tests/",
                    "    └── test_cli.py",
                ]
            ),
        )

    def test_files_only_shows_recency(self):

        output = format_context_tree(
            {
                "README.md": FileContextUsage(lines={1, 2}, hits=3, last_bubble_index=4),
                "cursor_chronicle/cli.py": FileContextUsage(
                    full_file=True,
                    hits=1,
                    last_bubble_index=0,
                ),
            },
            files_only=True,
            total_bubbles=5,
        )
        self.assertIn("README.md [3 read] [· · · · ·]", output)
        self.assertIn("cli.py [1 read] [·        ]", output)
        self.assertNotIn("cli.py [2 read", output)

    def test_files_only_shows_hit_count_when_reused(self):

        output = format_context_tree(
            {
                "README.md": FileContextUsage(lines={1, 2}, hits=3),
                "cursor_chronicle/cli.py": FileContextUsage(full_file=True, hits=1),
            },
            files_only=True,
        )
        self.assertIn("README.md [3 read]", output)
        self.assertIn("cli.py [1 read]", output)
        self.assertNotIn("cli.py [2 read]", output)

    def test_tree_shows_hit_count_when_reused(self):

        output = format_context_tree(
            {
                "README.md": FileContextUsage(
                    lines={1, 2},
                    hits=2,
                    last_bubble_index=1,
                ),
            },
            total_bubbles=2,
        )
        self.assertIn("README.md [2 read] [· · · · ·] — L1-L2", output)

    def test_color_output_includes_ansi_codes(self):

        output = format_context_tree(
            {
                "README.md": FileContextUsage(lines={1, 2}, hits=2),
                "cursor_chronicle/cli.py": FileContextUsage(
                    full_file=True,
                    edit_hits=1,
                    last_edit_bubble_index=0,
                ),
            },
            total_bubbles=2,
            color=True,
        )
        self.assertIn("\033[1m", output)
        self.assertIn("\033[36m", output)
        self.assertIn("\033[38;5;208m", output)
        self.assertIn("\033[92m", output)
        self.assertNotIn("\033[33m", output)
        self.assertIn("README.md", output)
        self.assertIn("L1-L2", output)
        self.assertIn("[1 edit]", output)
        self.assertIn("✓", output)

    def test_color_disabled_by_default(self):

        output = format_context_tree(
            {"README.md": FileContextUsage(lines={1, 2})},
        )
        self.assertNotIn("\033[", output)

    def test_collect_context_usage_counts_tool_invocations(self):
        messages = [
            {
                "type": 2,
                "tool_data": {
                    "name": "read_file_v2",
                    "status": "completed",
                    "rawArgs": {
                        "path": f"{PROJECT_ROOT}/file.py",
                        "limit": 5,
                    },
                    "result": {
                        "contents": "\n".join("x" for _ in range(5)),
                        "totalLinesInFile": 20,
                    },
                },
            },
            {
                "type": 2,
                "tool_data": {
                    "name": "read_file_v2",
                    "status": "completed",
                    "rawArgs": {
                        "path": f"{PROJECT_ROOT}/file.py",
                        "limit": 10,
                    },
                    "result": {
                        "contents": "\n".join("x" for _ in range(10)),
                        "totalLinesInFile": 20,
                    },
                },
            },
        ]
        usage = collect_context_usage(messages, project_root=PROJECT_ROOT)
        self.assertEqual(usage["file.py"].hits, 2)
        self.assertEqual(usage["file.py"].read_hits, 2)
        self.assertEqual(usage["file.py"].last_bubble_index, 1)

    def test_color_uses_distinct_greens_per_read_type(self):
        output = format_context_tree(
            {
                "read.py": FileContextUsage(
                    lines={1, 2},
                    hits=1,
                    read_hits=1,
                    read_lines={1, 2},
                ),
                "search.py": FileContextUsage(
                    lines={10},
                    hits=1,
                    search_hits=1,
                    search_lines={10},
                ),
                "semantic.py": FileContextUsage(
                    lines={20},
                    hits=1,
                    code_search_hits=1,
                    code_search_lines={20},
                ),
            },
            color=True,
        )
        self.assertIn("\033[92m[1 read]\033[0m", output)
        self.assertIn("\033[32m[1 search]\033[0m", output)
        self.assertIn("\033[38;5;77m[1 code search]\033[0m", output)
        self.assertIn("\033[92mL1-L2\033[0m", output)
        self.assertIn("\033[32mL10\033[0m", output)
        self.assertIn("\033[38;5;77mL20\033[0m", output)

if __name__ == "__main__":
    unittest.main()
