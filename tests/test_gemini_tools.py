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
    append_text_file,
    copy_file,
    copy_directory,
    calculator,
    count_file_lines,
    create_directory,
    current_datetime,
    edit_text_file,
    get_file_info,
    get_file_access_time,
    get_file_modified_time,
    get_file_extension,
    get_file_name,
    get_file_stem,
    get_file_parent,
    get_file_permissions,
    get_system_info,
    get_hostname,
    get_process_id,
    get_cpu_count,
    path_exists,
    hash_file,
    get_directory_entry_count,
    get_disk_usage,
    get_directory_size,
    delete_directory,
    delete_file,
    find_files,
    move_file,
    move_directory,
    search_text,
    write_text_file,
    list_directory,
    list_directory_recursive,
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
    def test_path_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                self.assertEqual(path_exists("notes.txt"), "true")
                self.assertEqual(path_exists("missing.txt"), "false")

    def test_path_exists_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    path_exists("../outside.txt")

    def test_path_exists_is_registered(self):
        self.assertIs(TOOL_HANDLERS["path_exists"], path_exists)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("path_exists", names)

    def test_creates_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = create_directory("archive/nested")
            self.assertEqual(result, "Created directory archive/nested")
            self.assertTrue((Path(directory) / "archive/nested").is_dir())

    def test_create_directory_rejects_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "archive").mkdir()
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "already exists"):
                    create_directory("archive")

    def test_create_directory_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    create_directory("../outside")

    def test_create_directory_is_registered(self):
        self.assertIs(TOOL_HANDLERS["create_directory"], create_directory)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("create_directory", names)

    def test_deletes_empty_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "archive").mkdir()
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = delete_directory("archive")
            self.assertEqual(result, "Deleted directory archive")
            self.assertFalse((root / "archive").exists())

    def test_delete_directory_rejects_non_empty_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "archive").mkdir()
            (root / "archive" / "note.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "not empty"):
                    delete_directory("archive")

    def test_delete_directory_rejects_missing_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    delete_directory("missing")

    def test_delete_directory_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    delete_directory("../outside")

    def test_delete_directory_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["delete_directory"], delete_directory)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("delete_directory", names)

    def test_gets_file_info(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = get_file_info("notes.txt")
            self.assertEqual(result, "Path: notes.txt\\nType: file\\nSize: 5 bytes")

    def test_get_file_info_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    get_file_info("missing.txt")

    def test_get_file_info_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_file_info"], get_file_info)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_file_info", names)

    def test_lists_directory_recursively(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "todo.txt").write_text("todo", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = list_directory_recursive()
            self.assertIn("directory: nested", result)
            self.assertIn("file: nested/todo.txt", result)
            self.assertIn("file: notes.txt", result)

    def test_list_directory_recursive_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    list_directory_recursive("../outside")

    def test_list_directory_recursive_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["list_directory_recursive"], list_directory_recursive)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("list_directory_recursive", names)

    def test_moves_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "archive"
            source.mkdir()
            (source / "note.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = move_directory("archive", "moved/archive")
            self.assertEqual(result, "Moved directory archive to moved/archive")
            self.assertFalse(source.exists())
            self.assertEqual(
                (root / "moved/archive/note.txt").read_text(encoding="utf-8"),
                "hello",
            )

    def test_move_directory_rejects_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "archive").mkdir()
            (root / "other").mkdir()
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "already exists"):
                    move_directory("archive", "other")

    def test_move_directory_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "archive").mkdir()
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    move_directory("archive", "../outside")

    def test_move_directory_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["move_directory"], move_directory)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("move_directory", names)

    def test_copies_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "archive"
            source.mkdir()
            (source / "note.txt").write_text("hello", encoding="utf-8")
            nested = source / "nested"
            nested.mkdir()
            (nested / "todo.txt").write_text("todo", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = copy_directory("archive", "copied/archive")
            self.assertEqual(result, "Copied directory archive to copied/archive")
            self.assertEqual((root / "archive/note.txt").read_text(encoding="utf-8"), "hello")
            self.assertEqual((root / "copied/archive/nested/todo.txt").read_text(encoding="utf-8"), "todo")

    def test_copy_directory_rejects_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "archive").mkdir()
            (root / "other").mkdir()
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "already exists"):
                    copy_directory("archive", "other")

    def test_copy_directory_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "archive").mkdir()
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    copy_directory("archive", "../outside")

    def test_copy_directory_rejects_destination_inside_source(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "archive").mkdir()
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "inside"):
                    copy_directory("archive", "archive/nested")

    def test_copy_directory_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["copy_directory"], copy_directory)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("copy_directory", names)

    def test_counts_file_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = count_file_lines("notes.txt")
            self.assertEqual(result, "3")

    def test_count_file_lines_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "Not a regular file"):
                    count_file_lines("missing.txt")

    def test_count_file_lines_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    count_file_lines("../outside.txt")

    def test_count_file_lines_is_registered(self):
        self.assertIs(TOOL_HANDLERS["count_file_lines"], count_file_lines)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("count_file_lines", names)

    def test_hashes_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = hash_file("notes.txt")
            self.assertEqual(
                result,
                "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
            )

    def test_hash_file_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "Not a regular file"):
                    hash_file("missing.txt")

    def test_hash_file_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    hash_file("../outside.txt")

    def test_hash_file_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["hash_file"], hash_file)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("hash_file", names)

    def test_get_disk_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = get_disk_usage(".")
            lines = result.splitlines()
            self.assertEqual(len(lines), 3)
            self.assertRegex(lines[0], r"^Total: \d+ bytes$")
            self.assertRegex(lines[1], r"^Used: \d+ bytes$")
            self.assertRegex(lines[2], r"^Free: \d+ bytes$")

    def test_get_disk_usage_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    get_disk_usage("missing")

    def test_get_disk_usage_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_disk_usage"], get_disk_usage)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_disk_usage", names)

    def test_get_directory_entry_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one.txt").write_text("1", encoding="utf-8")
            (root / "nested").mkdir()
            (root / "nested" / "two.txt").write_text("2", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                self.assertEqual(get_directory_entry_count("."), "2")

    def test_get_directory_entry_count_rejects_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one.txt").write_text("1", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "Not a directory"):
                    get_directory_entry_count("one.txt")

    def test_get_directory_entry_count_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    get_directory_entry_count("../outside")

    def test_get_directory_entry_count_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_directory_entry_count"], get_directory_entry_count)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_directory_entry_count", names)

    def test_get_directory_size(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_bytes(b"hello")
            nested = root / "nested"
            nested.mkdir()
            (nested / "todo.txt").write_bytes(b"todo")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = get_directory_size(".")
            self.assertEqual(result, "9 bytes")

    def test_get_directory_size_rejects_file(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "Not a directory"):
                    get_directory_size("notes.txt")

    def test_get_directory_size_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    get_directory_size("../outside")

    def test_get_directory_size_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_directory_size"], get_directory_size)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_directory_size", names)

    def test_get_file_access_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = get_file_access_time("notes.txt")
            parsed = __import__("datetime").datetime.fromisoformat(result)
            self.assertIsNotNone(parsed.tzinfo)

    def test_get_file_access_time_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    get_file_access_time("missing.txt")

    def test_get_file_access_time_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    get_file_access_time("../outside.txt")

    def test_get_file_access_time_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_file_access_time"], get_file_access_time)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_file_access_time", names)

    def test_get_file_modified_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "notes.txt"
            path.write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = get_file_modified_time("notes.txt")
            parsed = __import__("datetime").datetime.fromisoformat(result)
            self.assertIsNotNone(parsed.tzinfo)

    def test_get_file_stem(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.TXT").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                self.assertEqual(get_file_stem("notes.TXT"), "notes")

    def test_get_file_stem_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "Not a regular file"):
                    get_file_stem("missing.txt")

    def test_get_file_stem_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    get_file_stem("../outside.txt")

    def test_get_file_stem_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_file_stem"], get_file_stem)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_file_stem", names)

    def test_get_file_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            (root / "nested" / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                self.assertEqual(get_file_parent("nested/notes.txt"), "nested")
                self.assertEqual(get_file_parent("nested"), ".")

    def test_get_file_parent_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    get_file_parent("missing.txt")

    def test_get_file_parent_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    get_file_parent("../outside.txt")

    def test_get_file_parent_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_file_parent"], get_file_parent)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_file_parent", names)

    def test_get_file_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "notes.txt"
            path.write_text("hello", encoding="utf-8")
            path.chmod(0o640)
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                self.assertEqual(get_file_permissions("notes.txt"), "0640")

    def test_get_file_permissions_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    get_file_permissions("missing.txt")

    def test_get_file_permissions_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    get_file_permissions("../outside.txt")

    def test_get_file_permissions_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_file_permissions"], get_file_permissions)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_file_permissions", names)

    def test_get_file_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.TXT").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                self.assertEqual(get_file_extension("notes.TXT"), ".txt")

    def test_get_file_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            (root / "nested" / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                self.assertEqual(get_file_name("nested/notes.txt"), "notes.txt")
                self.assertEqual(get_file_name("nested"), "nested")

    def test_get_file_name_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    get_file_name("missing.txt")

    def test_get_file_name_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    get_file_name("../outside.txt")

    def test_get_file_name_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_file_name"], get_file_name)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_file_name", names)

    def test_get_file_extension_returns_empty_for_extensionless_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                self.assertEqual(get_file_extension("README"), "")

    def test_get_file_extension_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "Not a regular file"):
                    get_file_extension("missing.txt")

    def test_get_file_extension_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    get_file_extension("../outside.txt")

    def test_get_file_extension_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_file_extension"], get_file_extension)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_file_extension", names)

    def test_get_file_modified_time_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    get_file_modified_time("missing.txt")

    def test_get_file_modified_time_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    get_file_modified_time("../outside.txt")

    def test_get_file_modified_time_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_file_modified_time"], get_file_modified_time)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_file_modified_time", names)

    def test_get_hostname_returns_nonempty_value(self):
        self.assertTrue(get_hostname())

    def test_get_hostname_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_hostname"], get_hostname)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_hostname", names)

    def test_get_system_info_returns_runtime_details(self):
        result = get_system_info()
        self.assertRegex(result, r"^OS: .+\nArchitecture: .+\nPython: \d+\.\d+\.\d+$")

    def test_get_system_info_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_system_info"], get_system_info)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_system_info", names)

    def test_get_process_id_returns_positive_integer(self):
        self.assertGreater(int(get_process_id()), 0)

    def test_get_process_id_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_id"], get_process_id)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_process_id", names)

    def test_get_cpu_count_returns_positive_integer(self):
        self.assertGreater(int(get_cpu_count()), 0)

    def test_get_cpu_count_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_cpu_count"], get_cpu_count)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_cpu_count", names)

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
        self.assertEqual(names[names.index("path_exists"):names.index("find_files") + 1], [
            "path_exists", "create_directory", "delete_directory", "get_file_info", "get_file_access_time", "get_file_modified_time", "get_file_extension", "get_file_name", "get_file_stem", "get_file_permissions", "get_file_parent", "list_directory_recursive", "move_directory", "copy_directory", "hash_file", "count_file_lines", "get_directory_entry_count", "get_disk_usage", "get_directory_size", "list_directory", "read_text_file", "search_text", "write_text_file", "edit_text_file",
            "append_text_file", "copy_file", "move_file", "delete_file", "find_files"
        ])

    def test_copies_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = copy_file("notes.txt", "archive/notes.txt")
            self.assertEqual(result, "Copied notes.txt to archive/notes.txt")
            self.assertEqual((root / "notes.txt").read_text(encoding="utf-8"), "hello")
            self.assertEqual((root / "archive/notes.txt").read_text(encoding="utf-8"), "hello")

    def test_copy_rejects_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            (root / "other.txt").write_text("keep", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "already exists"):
                    copy_file("notes.txt", "other.txt")

    def test_copy_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    copy_file("notes.txt", "../outside.txt")

    def test_copy_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["copy_file"], copy_file)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("copy_file", names)

    def test_moves_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = move_file("notes.txt", "archive/notes.txt")
            self.assertEqual(result, "Moved notes.txt to archive/notes.txt")
            self.assertFalse((root / "notes.txt").exists())
            self.assertEqual(
                (root / "archive/notes.txt").read_text(encoding="utf-8"),
                "hello",
            )

    def test_move_rejects_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            (root / "other.txt").write_text("keep", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "already exists"):
                    move_file("notes.txt", "other.txt")

    def test_move_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    move_file("notes.txt", "../outside.txt")

    def test_move_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["move_file"], move_file)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("move_file", names)

    def test_deletes_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                self.assertEqual(delete_file("notes.txt"), "Deleted notes.txt")
            self.assertFalse((root / "notes.txt").exists())

    def test_delete_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    delete_file("../outside.txt")

    def test_delete_rejects_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    delete_file("missing.txt")

    def test_delete_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["delete_file"], delete_file)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("delete_file", names)

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

    def test_writes_text_file(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = write_text_file("notes/new.txt", "hello Nova")
                self.assertEqual(result, "Wrote 10 bytes to notes/new.txt")
                self.assertEqual((Path(directory) / "notes/new.txt").read_text(encoding="utf-8"), "hello Nova")

    def test_write_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    write_text_file("../outside.txt", "hello")

    def test_write_rejects_oversized_content(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "larger"):
                    write_text_file("large.txt", "x" * (64 * 1024 + 1))

    def test_write_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["write_text_file"], write_text_file)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("write_text_file", names)

    def test_edits_text_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello Nova", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = edit_text_file("notes.txt", "Nova", "world")
            self.assertEqual(result, "Edited notes.txt")
            self.assertEqual((root / "notes.txt").read_text(encoding="utf-8"), "hello world")

    def test_edit_rejects_missing_text(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "not found"):
                    edit_text_file("notes.txt", "missing", "world")

    def test_edit_rejects_ambiguous_text(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "notes.txt").write_text("hello hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "more than once"):
                    edit_text_file("notes.txt", "hello", "world")

    def test_edit_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["edit_text_file"], edit_text_file)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("edit_text_file", names)

    def test_appends_text_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = append_text_file("notes.txt", " Nova")
                self.assertEqual(result, "Appended 5 bytes to notes.txt")
                self.assertEqual((root / "notes.txt").read_text(encoding="utf-8"), "hello Nova")

    def test_append_creates_missing_file_and_parents(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                append_text_file("notes/new.txt", "first")
                append_text_file("notes/new.txt", " second")
                self.assertEqual(
                    (Path(directory) / "notes/new.txt").read_text(encoding="utf-8"),
                    "first second",
                )

    def test_append_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    append_text_file("../outside.txt", "hello")

    def test_append_rejects_oversized_content(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "larger"):
                    append_text_file("large.txt", "x" * (64 * 1024 + 1))

    def test_append_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["append_text_file"], append_text_file)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("append_text_file", names)

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
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertEqual(names[names.index("search_text")], "search_text")

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
