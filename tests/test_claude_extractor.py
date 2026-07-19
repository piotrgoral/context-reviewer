"""Tests for Claude Code context extraction."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from context_reviewer.agents.claude.context import build_context_tree, last_user_bubble_index
from context_reviewer.agents.claude.extractor import collect_context_usage
from context_reviewer.agents.claude.messages import BUBBLE_TYPE_USER, load_session_messages
from tests.claude_fixtures import PROJECT_ROOT, SESSION, sample_messages

SESSION_MESSAGES = load_session_messages(SESSION, include_subagents=False)


class TestClaudeContextExtractionFromFixtures(unittest.TestCase):
    def test_read_usage_from_fixture_session(self):
        usage = collect_context_usage(SESSION_MESSAGES, PROJECT_ROOT)
        self.assertIn("src/app.py", usage)
        self.assertGreater(usage["src/app.py"].read_hits, 0)
        self.assertEqual(usage["src/app.py"].lines, {1, 2, 3})

    def test_edit_usage_from_fixture_session(self):
        usage = collect_context_usage(SESSION_MESSAGES, PROJECT_ROOT)
        self.assertIn("src/app.py", usage)
        self.assertGreater(usage["src/app.py"].edit_hits, 0)
        self.assertIn(10, usage["src/app.py"].edit_lines)

    def test_write_usage_from_fixture_session(self):
        usage = collect_context_usage(SESSION_MESSAGES, PROJECT_ROOT)
        self.assertIn("src/new.py", usage)
        self.assertTrue(usage["src/new.py"].edit_full_file)

    def test_last_user_bubble_ignores_tool_results(self):
        index = last_user_bubble_index(SESSION_MESSAGES)
        self.assertIsNotNone(index)
        self.assertEqual(SESSION_MESSAGES[index]["type"], BUBBLE_TYPE_USER)
        self.assertEqual(SESSION_MESSAGES[index]["text"], "follow up question")

    def test_last_turn_limits_to_post_user_activity(self):
        tree = build_context_tree(SESSION_MESSAGES, PROJECT_ROOT, last_turn=True)
        self.assertIsNone(tree.empty_message)
        self.assertEqual(tree.total_bubbles, 1)
        self.assertIn("src/other.py", tree.usage)
        self.assertNotIn("src/app.py", tree.usage)


class TestClaudeContextExtractionInline(unittest.TestCase):
    def test_collect_context_usage_from_normalized_bubbles(self):
        usage = collect_context_usage(sample_messages(include_follow_up=False), PROJECT_ROOT)
        self.assertIn("src/app.py", usage)
        self.assertIn("src/new.py", usage)
        self.assertGreater(usage["src/app.py"].read_hits, 0)
        self.assertGreater(usage["src/app.py"].edit_hits, 0)


if __name__ == "__main__":
    unittest.main()
