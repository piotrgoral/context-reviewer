"""Tests for tool_results.py module."""

import base64
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from context_reviewer.agents.cursor.tool_results import (
    extract_code_search_matches,
    extract_line_matches_from_binary,
    extract_matches_from_code_results,
    extract_matches_from_grep_search_result,
    extract_matches_from_json_result,
    extract_search_matches,
    is_code_search_tool,
    is_search_tool,
)


def _encode_line_match(line_number: int, content: str) -> bytes:
    line_bytes = _encode_varint(line_number)
    content_bytes = content.encode("utf-8")
    return b"\x08" + line_bytes + b"\x12" + _encode_varint(len(content_bytes)) + content_bytes


def _encode_varint(value: int) -> bytes:
    result = bytearray()
    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value & 0x7F)
    return bytes(result)


class TestSearchToolDetection(unittest.TestCase):
    def test_is_search_tool(self):
        self.assertTrue(is_search_tool("ripgrep_raw_search"))
        self.assertTrue(is_search_tool("grep_search"))
        self.assertFalse(is_search_tool("read_file_v2"))

    def test_is_code_search_tool(self):
        self.assertTrue(is_code_search_tool("codebase_search"))
        self.assertTrue(is_code_search_tool("semantic_search_full"))
        self.assertFalse(is_code_search_tool("grep"))


class TestSearchBinaryExtraction(unittest.TestCase):
    def test_extract_line_matches_from_binary(self):
        payload = _encode_line_match(35, "python -m context_reviewer --help") + _encode_line_match(
            498, "cursor-chronicle"
        )
        matches = extract_line_matches_from_binary(payload)
        self.assertEqual(
            matches,
            [
                (35, "python -m context_reviewer --help"),
                (498, "cursor-chronicle"),
            ],
        )


class TestWorkspaceJsonExtraction(unittest.TestCase):
    def test_extract_matches_from_json_result(self):
        result_data = {
            "workspaceResults": {
                "folder": {
                    "content": {
                        "matches": [
                            {
                                "file": "README.md",
                                "matches": [
                                    {"lineNumber": 35, "content": "hello"},
                                ],
                            }
                        ]
                    }
                }
            }
        }
        matches = extract_matches_from_json_result(result_data)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].line_number, 35)
        self.assertEqual(matches[0].file, "README.md")

    def test_extract_search_matches_from_json(self):
        tool_data = {
            "name": "ripgrep_raw_search",
            "result": {
                "success": {
                    "workspaceResults": {
                        "folder": {
                            "content": {
                                "matches": [
                                    {
                                        "file": "app.py",
                                        "matches": [
                                            {"lineNumber": 10, "content": "def main"},
                                        ],
                                    }
                                ]
                            }
                        }
                    }
                }
            },
        }
        matches = extract_search_matches(tool_data)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].line_number, 10)


class TestGrepSearchExtraction(unittest.TestCase):
    def test_extract_matches_from_grep_search_result(self):
        result_data = {
            "internal": {
                "results": [
                    {
                        "resource": "file:///tmp/README.md",
                        "results": [
                            {
                                "match": {
                                    "previewText": "hello",
                                    "rangeLocations": [
                                        {"source": {"startLineNumber": 5}}
                                    ],
                                }
                            }
                        ],
                    }
                ]
            }
        }
        matches = extract_matches_from_grep_search_result(result_data)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].line_number, 5)
        self.assertEqual(matches[0].file, "README.md")


class TestCodeSearchExtraction(unittest.TestCase):
    def test_extract_matches_from_code_results(self):
        result_data = {
            "codeResults": [
                {
                    "codeBlock": {
                        "relativeWorkspacePath": "src/app.py",
                        "detailedLines": [
                            {"lineNumber": 1, "text": "import os"},
                            {"lineNumber": 2, "text": "pass"},
                        ],
                    }
                }
            ]
        }
        matches = extract_matches_from_code_results(result_data)
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].line_number, 1)

    def test_extract_code_search_matches(self):
        tool_data = {
            "name": "codebase_search",
            "result": {
                "codeResults": [
                    {
                        "codeBlock": {
                            "relativeWorkspacePath": "src/app.py",
                            "detailedLines": [
                                {"lineNumber": 10, "text": "def main():"},
                            ],
                        }
                    }
                ]
            },
        }
        matches = extract_code_search_matches(tool_data)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].line_number, 10)


if __name__ == "__main__":
    unittest.main()
