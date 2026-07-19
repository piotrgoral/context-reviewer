"""Tests for Claude Code CLI integration."""

import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from context_reviewer.agents.claude.viewer import ClaudeSessionViewer
from context_reviewer.cli import create_parser, main, show_context_tree
from tests.claude_fixtures import FIXTURES, PROJECT_ROOT, sample_messages


class TestClaudeParser(unittest.TestCase):
    def test_claude_flag_parses(self):
        args = create_parser().parse_args(["--claude"])
        self.assertTrue(args.claude)
        self.assertFalse(args.cursor)

    def test_agent_flag_is_required(self):
        with self.assertRaises(SystemExit):
            create_parser().parse_args([])


class TestClaudeCli(unittest.TestCase):
    def _capture_output(self, func, *args, **kwargs):
        captured = StringIO()
        stdout = sys.stdout
        sys.stdout = captured
        try:
            func(*args, **kwargs)
        finally:
            sys.stdout = stdout
        return captured.getvalue()

    def test_list_all_rejected_for_claude(self):
        with patch("sys.argv", ["context-reviewer", "--claude", "--list-all"]):
            with patch("sys.exit") as mock_exit:
                main()
                mock_exit.assert_called_once_with(1)

    def test_context_tree_with_fixture_directory(self):
        viewer = ClaudeSessionViewer(projects_root=FIXTURES, flat_layout=True)
        output = self._capture_output(
            show_context_tree,
            viewer,
            project_name="project",
            agent="claude",
        )
        self.assertIn("root", output)
        self.assertIn("app.py", output)

    @patch("context_reviewer.cli.format_context_tree")
    def test_context_tree_with_mocked_viewer(self, mock_format):
        mock_format.return_value = "root\n└── src/app.py"
        viewer = MagicMock()
        viewer.get_projects.return_value = [
            {
                "project_name": "demo",
                "folder_path": PROJECT_ROOT,
                "sessions": [
                    {
                        "session_id": "abc",
                        "name": "demo",
                        "lastUpdatedAt": 1000,
                    }
                ],
            }
        ]
        viewer.get_session_messages.return_value = sample_messages(include_follow_up=False)
        output = self._capture_output(
            show_context_tree,
            viewer,
            project_name="demo",
            agent="claude",
        )
        self.assertIn("root", output)
        mock_format.assert_called_once()


if __name__ == "__main__":
    unittest.main()
