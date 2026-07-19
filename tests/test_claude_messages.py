"""Tests for Claude Code message normalization."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from context_reviewer.agents.claude.messages import (
    BUBBLE_TYPE_ASSISTANT,
    BUBBLE_TYPE_USER,
    load_session_bubbles,
    load_session_messages,
)
from context_reviewer.agents.claude.utils import is_meta_user_content
from tests.claude_fixtures import SESSION

PROJECT_ROOT = "/tmp/project"


class TestMetaUserContent(unittest.TestCase):
    def test_meta_prefixes_are_ignored(self):
        self.assertTrue(is_meta_user_content("<command-name>/model</command-name>"))
        self.assertTrue(is_meta_user_content("<task-notification>done</task-notification>"))
        self.assertFalse(is_meta_user_content("please refactor this module"))


class TestClaudeMessageLoading(unittest.TestCase):
    def test_pairs_tool_calls_with_results(self):
        bubbles = load_session_bubbles(SESSION)
        read_bubble = next(
            bubble
            for bubble in bubbles
            if (bubble.get("tool_data") or {}).get("name") == "Read"
            and (bubble.get("tool_data") or {}).get("input", {}).get("file_path", "").endswith(
                "app.py"
            )
        )
        self.assertEqual(read_bubble["type"], BUBBLE_TYPE_ASSISTANT)
        self.assertIn("file", read_bubble["tool_data"]["result"])

    def test_user_prompts_exclude_tool_results_and_meta(self):
        bubbles = load_session_bubbles(SESSION)
        user_bubbles = [bubble for bubble in bubbles if bubble.get("type") == BUBBLE_TYPE_USER]
        self.assertEqual(
            [bubble["text"] for bubble in user_bubbles],
            ["please refactor this module", "follow up question"],
        )
        for bubble in user_bubbles:
            self.assertIsInstance(bubble.get("text"), str)
            self.assertIsNone(bubble.get("tool_data"))
            self.assertFalse(is_meta_user_content(bubble["text"]))

    def test_subagents_are_merged(self):
        with_sub = load_session_messages(SESSION, include_subagents=True)
        without_sub = load_session_messages(SESSION, include_subagents=False)
        self.assertGreater(len(with_sub), len(without_sub))
        self.assertTrue(
            any(
                (bubble.get("tool_data") or {}).get("input", {}).get("file_path", "").endswith(
                    "subagent.py"
                )
                for bubble in with_sub
            )
        )


if __name__ == "__main__":
    unittest.main()
