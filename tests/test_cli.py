"""Tests for context-reviewer CLI."""

import argparse
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from context_reviewer.agents.cursor.presentation import print_all_dialogs
from context_reviewer.agents.cursor.viewer import CursorChatViewer
from context_reviewer.cli import (
    create_parser,
    parse_positive_int,
    resolve_use_color,
    show_context_tree,
)


class TestCreateParser(unittest.TestCase):
    def test_files_only_arg(self):
        self.assertTrue(
            create_parser().parse_args(["--cursor", "--files-only"]).files_only
        )
        self.assertFalse(create_parser().parse_args(["--cursor"]).files_only)

    def test_edits_arg(self):
        self.assertTrue(create_parser().parse_args(["--cursor", "--edits"]).edits)
        self.assertFalse(create_parser().parse_args(["--cursor"]).edits)

    def test_context_tree_depth_arg(self):
        args = create_parser().parse_args(
            ["--cursor", "--context-tree-depth", "2"]
        )
        self.assertEqual(args.context_tree_depth, 2)
        self.assertIsNone(
            create_parser().parse_args(["--cursor"]).context_tree_depth
        )

    def test_context_tree_depth_must_be_positive(self):
        with self.assertRaises(SystemExit):
            create_parser().parse_args(["--cursor", "--context-tree-depth", "0"])

    def test_last_turn_arg(self):
        self.assertTrue(create_parser().parse_args(["--cursor", "--last-turn"]).last_turn)
        self.assertFalse(create_parser().parse_args(["--cursor"]).last_turn)

    def test_color_args(self):
        self.assertTrue(create_parser().parse_args(["--cursor", "--color"]).color)
        self.assertFalse(create_parser().parse_args(["--cursor", "--no-color"]).color)
        self.assertIsNone(create_parser().parse_args(["--cursor"]).color)

    def test_cursor_required_for_main(self):
        with patch("sys.argv", ["context-reviewer"]):
            with patch("sys.exit") as mock_exit:
                from context_reviewer.cli import main

                main()
                mock_exit.assert_called_once_with(2)


class TestResolveUseColor(unittest.TestCase):
    def test_explicit_true(self):
        self.assertTrue(resolve_use_color(True))

    def test_explicit_false(self):
        self.assertFalse(resolve_use_color(False))

    @patch.dict("os.environ", {"NO_COLOR": "1"}, clear=True)
    def test_no_color_env(self):
        self.assertFalse(resolve_use_color(None))

    @patch.dict("os.environ", {"FORCE_COLOR": "1"}, clear=True)
    def test_force_color_env(self):
        self.assertTrue(resolve_use_color(None))

    @patch("context_reviewer.cli.sys.stdout")
    @patch.dict("os.environ", {}, clear=True)
    def test_tty_detection(self, mock_stdout):
        mock_stdout.isatty.return_value = True
        self.assertTrue(resolve_use_color(None))
        mock_stdout.isatty.return_value = False
        self.assertFalse(resolve_use_color(None))


class TestParsePositiveIntFunction(unittest.TestCase):
    def test_valid_value(self):
        self.assertEqual(parse_positive_int("5"), 5)

    def test_invalid_zero(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_positive_int("0")


class TestShowContextTree(unittest.TestCase):
    def _capture_output(self, func, *args, **kwargs):
        captured = StringIO()
        sys.stdout = captured
        try:
            func(*args, **kwargs)
        finally:
            sys.stdout = sys.__stdout__
        return captured.getvalue()

    def test_no_projects(self):
        viewer = MagicMock()
        viewer.get_projects.return_value = []
        output = self._capture_output(show_context_tree, viewer, agent="cursor")
        self.assertIn("No projects found", output)

    def test_project_not_found(self):
        viewer = MagicMock()
        viewer.get_projects.return_value = [
            {"project_name": "other-project", "composers": []}
        ]
        output = self._capture_output(
            show_context_tree, viewer, project_name="nonexistent", agent="cursor"
        )
        self.assertIn("not found", output)

    def test_context_tree_output(self):
        viewer = MagicMock()
        viewer.get_projects.return_value = [
            {
                "project_name": "test-project",
                "folder_path": "/tmp/project",
                "composers": [
                    {
                        "name": "test-dialog",
                        "composerId": "abc123",
                        "lastUpdatedAt": 1000,
                    }
                ],
            }
        ]
        viewer.get_dialog_messages.return_value = [
            {
                "type": 2,
                "tool_data": {
                    "name": "read_file_v2",
                    "status": "completed",
                    "rawArgs": {
                        "path": "/tmp/project/app.py",
                        "limit": 5,
                    },
                    "result": {
                        "contents": "\n".join("x" for _ in range(5)),
                        "totalLinesInFile": 20,
                    },
                },
            },
        ]
        output = self._capture_output(
            show_context_tree,
            viewer,
            project_name="test-project",
            agent="cursor",
        )
        self.assertIn("root", output)
        self.assertIn("app.py [1 read] — L1-L5", output)

    def test_context_files_only_output(self):
        viewer = MagicMock()
        viewer.get_projects.return_value = [
            {
                "project_name": "test-project",
                "folder_path": "/tmp/project",
                "composers": [
                    {
                        "name": "test-dialog",
                        "composerId": "abc123",
                        "lastUpdatedAt": 1000,
                    }
                ],
            }
        ]
        viewer.get_dialog_messages.return_value = [
            {
                "type": 2,
                "tool_data": {
                    "name": "read_file_v2",
                    "status": "completed",
                    "rawArgs": {
                        "path": "/tmp/project/app.py",
                        "limit": 5,
                    },
                    "result": {
                        "contents": "\n".join("x" for _ in range(5)),
                        "totalLinesInFile": 20,
                    },
                },
            },
        ]
        output = self._capture_output(
            show_context_tree,
            viewer,
            project_name="test-project",
            files_only=True,
            agent="cursor",
        )
        self.assertIn("root", output)
        self.assertIn("app.py", output)
        self.assertNotIn("L1-L5", output)
        self.assertNotIn(" — ", output)

    @patch("context_reviewer.cli.format_context_tree")
    def test_edits_mode_passes_mode_to_formatter(self, mock_format):
        mock_format.return_value = "root"
        viewer = MagicMock()
        viewer.get_projects.return_value = [
            {
                "project_name": "test-project",
                "folder_path": "/tmp/project",
                "composers": [
                    {
                        "name": "test-dialog",
                        "composerId": "abc123",
                        "lastUpdatedAt": 1000,
                    }
                ],
            }
        ]
        viewer.get_dialog_messages.return_value = [{"type": 1, "text": "hello"}]
        self._capture_output(
            show_context_tree,
            viewer,
            project_name="test-project",
            mode="edits",
            agent="cursor",
        )
        mock_format.assert_called_once()
        self.assertEqual(mock_format.call_args.kwargs["mode"], "edits")


class TestPrintAllDialogs(unittest.TestCase):
    def _capture_output(self, func, *args, **kwargs):
        captured = StringIO()
        sys.stdout = captured
        try:
            func(*args, **kwargs)
        finally:
            sys.stdout = sys.__stdout__
        return captured.getvalue()

    def test_dialog_filter_and_sort_by_name_together(self):
        # Regression test: get_all_dialogs takes 7 params (start_date, end_date,
        # project_filter, dialog_filter, sort_by, sort_desc, use_updated) and
        # previously print_all_dialogs's predecessor called it with dialog_filter
        # omitted, shifting sort_by/sort_desc/use_updated one slot left.
        viewer = CursorChatViewer.__new__(CursorChatViewer)
        viewer.get_projects = MagicMock(
            return_value=[
                {
                    "project_name": "proj",
                    "folder_path": "/tmp/proj",
                    "composers": [
                        {
                            "name": "zeta chat",
                            "composerId": "z1",
                            "lastUpdatedAt": 3,
                            "createdAt": 3,
                        },
                        {
                            "name": "alpha chat",
                            "composerId": "a1",
                            "lastUpdatedAt": 1,
                            "createdAt": 1,
                        },
                        {
                            "name": "other",
                            "composerId": "o1",
                            "lastUpdatedAt": 2,
                            "createdAt": 2,
                        },
                    ],
                }
            ]
        )

        output = self._capture_output(
            print_all_dialogs,
            viewer,
            dialog_filter="chat",
            sort_by="name",
        )

        self.assertIn("alpha chat", output)
        self.assertIn("zeta chat", output)
        self.assertNotIn("other", output)
        self.assertLess(output.index("alpha chat"), output.index("zeta chat"))


if __name__ == "__main__":
    unittest.main()
