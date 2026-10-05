"""Offline tests for Nova's local tools."""

import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gemini_agent.tools import (
    TOOL_DECLARATIONS,
    TOOL_HANDLERS,
    calculator,
    current_datetime,
    find_files,
    search_text,
    list_directory,
    read_text_file,
)


class CalculatorTests(unittest.TestCase):
    def test_basic_arithmetic(self):
        self.assertEqual(calculator("12 * (3 + 4)"), "84")

    def test_decimal_arithmetic(self):
        self.assertEqual(calculator("10 / 4"), "2.5")

    def test_rejects_python(self):
        with self.assertRaises(ValueError):
            calculator("__import__('os').getcwd()")

    def test_calculator_is_registered(self):
        self.assertIs(TOOL_HANDLERS["calculator"], calculator)
        self.assertEqual(TOOL_DECLARATIONS[0]["name"], "calculator")


class DateTimeToolTests(unittest.TestCase):
    def test_current_datetime_is_registered(self):
        self.assertIs(TOOL_HANDLERS["current_datetime"], current_datetime)
        self.assertEqual(TOOL_DECLARATIONS[1]["name"], "current_datetime")

    def test_current_datetime_has_iso_format(self):
        value = current_datetime()
        self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")


class FilesystemToolTests(unittest.TestCase):
    def test_lists_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            (root / "subdir").mkdir()
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = list_directory()
        self.assertIn("file: notes.txt", result)
        self.assertIn("directory: subdir", result)

    def test_reads_text_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello Nova", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                self.assertEqual(read_text_file("notes.txt"), "hello Nova")

    def test_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    read_text_file("../outside.txt")

    def test_rejects_oversized_text_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.txt"
            path.write_bytes(b"x" * (64 * 1024 + 1))
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "larger"):
                    read_text_file("large.txt")

    def test_filesystem_tools_are_registered(self):
        self.assertIs(TOOL_HANDLERS["list_directory"], list_directory)
        self.assertIs(TOOL_HANDLERS["read_text_file"], read_text_file)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertEqual(names[names.index("list_directory"):names.index("find_files") + 1], [
            "list_directory", "read_text_file", "search_text", "find_files"
        ])

    def test_finds_files_by_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            (root / "image.png").write_bytes(b"data")
            nested = root / "nested"
            nested.mkdir()
            (nested / "todo.txt").write_text("todo", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = find_files("*.txt")
        self.assertIn("notes.txt", result)
        self.assertIn("nested/todo.txt", result)
        self.assertNotIn("image.png", result)


    def test_searches_text_in_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello Nova\nsecond line", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "todo.txt").write_text("HELLO again", encoding="utf-8")
            (root / "binary.bin").write_bytes(b"\x00hello")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = search_text("hello")
        self.assertIn("notes.txt:1: hello Nova", result)
        self.assertIn("nested/todo.txt:1: HELLO again", result)
        self.assertNotIn("binary.bin", result)

    def test_search_rejects_empty_pattern(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "empty"):
                    search_text("")

    def test_search_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    search_text("hello", "../")

    def test_search_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["search_text"], search_text)
        self.assertEqual(TOOL_DECLARATIONS[-2]["name"], "search_text")

    def test_find_rejects_empty_pattern(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "empty"):
                    find_files("")

    def test_find_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    find_files("*.txt", "../")

    def test_find_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["find_files"], find_files)
        self.assertEqual(TOOL_DECLARATIONS[-1]["name"], "find_files")


if __name__ == "__main__":
    unittest.main()
