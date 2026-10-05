"""Offline tests for Nova's local tools."""

import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gemini_agent.tools import (
    RUN_COMMAND_DECLARATION,
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
    get_system_battery_status,
    get_hostname,
    get_network_addresses,
    get_network_interfaces,
    get_load_average,
    get_system_memory_usage,
    get_system_cpu_usage,
    get_system_swap_usage,
    get_system_boot_time,
    get_system_uptime,
    get_process_id,
    get_current_working_directory,
    get_python_executable,
    get_cpu_count,
    get_memory_usage,
    get_temp_directory,
    get_home_directory,
    get_umask,
    get_process_uptime,
    get_process_thread_count,
    get_parent_process_id,
    get_process_group_id,
    get_session_id,
    get_user_id,
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
    run_command,
    list_processes,
    get_process_status,
    get_process_command_line,
    get_process_executable,
    get_process_working_directory,
    get_process_parent_name,
    get_process_start_time,
    get_process_cpu_time,
    get_process_memory_usage,
    get_process_nice,
)



class ListProcessesToolTests(unittest.TestCase):
    def test_list_processes_returns_pid_and_name(self):
        result = list_processes()
        self.assertTrue(result)
        self.assertTrue(all(line.split(maxsplit=1)[0].isdigit() for line in result.splitlines()))

    def test_list_processes_is_registered(self):
        self.assertIs(TOOL_HANDLERS["list_processes"], list_processes)
        self.assertNotEqual(TOOL_DECLARATIONS[-1]["name"], "list_processes")


class GetProcessStatusToolTests(unittest.TestCase):
    def test_get_process_status_returns_basic_status(self):
        result = get_process_status(str(os.getpid()))
        self.assertIn(f"PID: {os.getpid()}", result)
        self.assertIn("Name:", result)
        self.assertIn("State:", result)

    def test_get_process_status_rejects_invalid_pid(self):
        with self.assertRaisesRegex(ValueError, "PID"):
            get_process_status("not-a-pid")

    def test_get_process_status_rejects_missing_process(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            get_process_status("999999999")

    def test_get_process_status_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_status"], get_process_status)

class GetProcessExecutableToolTests(unittest.TestCase):
    def test_get_process_executable_returns_path(self):
        result = get_process_executable(str(os.getpid()))
        self.assertTrue(result)
        self.assertIn("python", result.lower())

    def test_get_process_executable_rejects_invalid_pid(self):
        with self.assertRaisesRegex(ValueError, "PID"):
            get_process_executable("not-a-pid")

    def test_get_process_executable_rejects_missing_process(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            get_process_executable("999999999")

    def test_get_process_executable_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_executable"], get_process_executable)


class GetProcessWorkingDirectoryToolTests(unittest.TestCase):
    def test_get_process_working_directory_returns_path(self):
        result = get_process_working_directory(str(os.getpid()))
        self.assertTrue(result)
        self.assertEqual(result, os.getcwd())

    def test_get_process_working_directory_rejects_invalid_pid(self):
        with self.assertRaisesRegex(ValueError, "PID"):
            get_process_working_directory("not-a-pid")

    def test_get_process_working_directory_rejects_missing_process(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            get_process_working_directory("999999999")

    def test_get_process_working_directory_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_working_directory"], get_process_working_directory)


class GetProcessParentNameToolTests(unittest.TestCase):
    def test_get_process_parent_name_returns_name(self):
        result = get_process_parent_name(str(os.getpid()))
        self.assertTrue(result)

    def test_get_process_parent_name_rejects_invalid_pid(self):
        with self.assertRaisesRegex(ValueError, "PID"):
            get_process_parent_name("not-a-pid")

    def test_get_process_parent_name_rejects_missing_process(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            get_process_parent_name("999999999")

    def test_get_process_parent_name_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_parent_name"], get_process_parent_name)


class GetProcessStartTimeToolTests(unittest.TestCase):
    def test_get_process_start_time_returns_iso_time(self):
        result = get_process_start_time(str(os.getpid()))
        self.assertRegex(result, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")

    def test_get_process_start_time_rejects_invalid_pid(self):
        with self.assertRaisesRegex(ValueError, "PID"):
            get_process_start_time("not-a-pid")

    def test_get_process_start_time_rejects_missing_process(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            get_process_start_time("999999999")

    def test_get_process_start_time_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_start_time"], get_process_start_time)




class GetProcessCpuTimeToolTests(unittest.TestCase):
    def test_get_process_cpu_time_returns_components(self):
        result = get_process_cpu_time(str(os.getpid()))
        self.assertRegex(result, r"^User: \d+\.\d{3} seconds\nSystem: \d+\.\d{3} seconds\nTotal: \d+\.\d{3} seconds$")

    def test_get_process_cpu_time_rejects_invalid_pid(self):
        with self.assertRaisesRegex(ValueError, "PID"):
            get_process_cpu_time("not-a-pid")

    def test_get_process_cpu_time_rejects_missing_process(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            get_process_cpu_time("999999999")

    def test_get_process_cpu_time_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_cpu_time"], get_process_cpu_time)


class GetProcessMemoryUsageToolTests(unittest.TestCase):
    def test_get_process_memory_usage_returns_positive_bytes(self):
        result = get_process_memory_usage(str(os.getpid()))
        self.assertGreater(int(result), 0)

    def test_get_process_memory_usage_rejects_invalid_pid(self):
        with self.assertRaisesRegex(ValueError, "PID"):
            get_process_memory_usage("not-a-pid")

    def test_get_process_memory_usage_rejects_missing_process(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            get_process_memory_usage("999999999")

    def test_get_process_memory_usage_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_memory_usage"], get_process_memory_usage)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_process_memory_usage", names)


class GetNetworkAddressesToolTests(unittest.TestCase):
    def test_get_network_addresses_returns_nonempty_value(self):
        result = get_network_addresses()
        self.assertTrue(result)

    def test_get_network_addresses_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_network_addresses"], get_network_addresses)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_network_addresses", names)


class GetNetworkInterfacesToolTests(unittest.TestCase):
    def test_get_network_interfaces_returns_nonempty_value(self):
        result = get_network_interfaces()
        self.assertTrue(result)
        self.assertIn(":", result)

    def test_get_network_interfaces_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_network_interfaces"], get_network_interfaces)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_network_interfaces", names)


class GetLoadAverageToolTests(unittest.TestCase):
    def test_get_load_average_returns_three_values(self):
        result = get_load_average()
        self.assertRegex(result, r"^1m: -?\d+\.\d{2}\n5m: -?\d+\.\d{2}\n15m: -?\d+\.\d{2}$")

    def test_get_load_average_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_load_average"], get_load_average)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_load_average", names)


class GetProcessNiceToolTests(unittest.TestCase):
    def test_get_process_nice_returns_integer(self):
        result = get_process_nice(str(os.getpid()))
        self.assertRegex(result, r"^-?\d+$")

    def test_get_process_nice_rejects_invalid_pid(self):
        with self.assertRaisesRegex(ValueError, "PID"):
            get_process_nice("not-a-pid")

    def test_get_process_nice_rejects_missing_process(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            get_process_nice("999999999")

    def test_get_process_nice_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_nice"], get_process_nice)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_process_nice", names)


class GetProcessCommandLineToolTests(unittest.TestCase):
    def test_get_process_command_line_returns_command(self):
        result = get_process_command_line(str(os.getpid()))
        self.assertTrue(result)
        self.assertIn("python", result.lower())

    def test_get_process_command_line_rejects_invalid_pid(self):
        with self.assertRaisesRegex(ValueError, "PID"):
            get_process_command_line("not-a-pid")

    def test_get_process_command_line_rejects_missing_process(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            get_process_command_line("999999999")

    def test_get_process_command_line_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_command_line"], get_process_command_line)


class RunCommandToolTests(unittest.TestCase):
    def test_run_command_executes_approved_command(self):
        with patch(
            "gemini_agent.tools.subprocess.run",
            return_value=type("Result", (), {
                "returncode": 0,
                "stdout": "hello\n",
                "stderr": "",
            })(),
        ) as run:
            result = run_command("pwd")
        self.assertEqual(result, "Exit code: 0\nstdout:\nhello")
        run.assert_called_once()

    def test_run_command_rejects_unapproved_command(self):
        with self.assertRaisesRegex(ValueError, "Command is not allowed"):
            run_command("rm file.txt")

    def test_run_command_rejects_unapproved_arguments(self):
        with self.assertRaisesRegex(ValueError, "Arguments are not allowed"):
            run_command("git log")

    def test_run_command_is_registered(self):
        self.assertIs(TOOL_HANDLERS["run_command"], run_command)
        self.assertEqual(RUN_COMMAND_DECLARATION["name"], "run_command")

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


class CurrentWorkingDirectoryToolTests(unittest.TestCase):
    def test_current_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False), patch("os.getcwd", return_value=directory):
                self.assertEqual(get_current_working_directory(), directory)

    def test_current_working_directory_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_current_working_directory"], get_current_working_directory)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_current_working_directory", names)

    def test_python_executable(self):
        with patch("os.sys.executable", "/data/data/com.termux/files/usr/bin/python"):
            self.assertEqual(get_python_executable(), "/data/data/com.termux/files/usr/bin/python")

    def test_python_executable_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_python_executable"], get_python_executable)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_python_executable", names)

    def test_memory_usage_returns_positive_bytes(self):
        self.assertGreater(int(get_memory_usage()), 0)

    def test_memory_usage_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_memory_usage"], get_memory_usage)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_memory_usage", names)

    def test_temp_directory_returns_nonempty_path(self):
        self.assertTrue(get_temp_directory())

    def test_temp_directory_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_temp_directory"], get_temp_directory)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_temp_directory", names)

    def test_process_thread_count_returns_positive_integer(self):
        self.assertGreater(int(get_process_thread_count()), 0)

    def test_process_thread_count_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_thread_count"], get_process_thread_count)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_process_thread_count", names)

    def test_user_id_returns_nonnegative_integer(self):
        self.assertGreaterEqual(int(get_user_id()), 0)

    def test_user_id_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_user_id"], get_user_id)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_user_id", names)

    def test_session_id_returns_positive_integer(self):
        self.assertGreater(int(get_session_id()), 0)

    def test_session_id_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_session_id"], get_session_id)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_session_id", names)

    def test_process_group_id_returns_positive_integer(self):
        self.assertGreater(int(get_process_group_id()), 0)

    def test_process_group_id_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_group_id"], get_process_group_id)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_process_group_id", names)

    def test_parent_process_id_returns_positive_integer(self):
        self.assertGreater(int(get_parent_process_id()), 0)

    def test_parent_process_id_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_parent_process_id"], get_parent_process_id)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_parent_process_id", names)


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

    def test_get_home_directory_returns_nonempty_value(self):
        self.assertTrue(get_home_directory())
        self.assertEqual(get_home_directory(), str(Path.home()))

    def test_get_home_directory_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_home_directory"], get_home_directory)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_home_directory", names)

    def test_get_process_uptime_returns_nonnegative_seconds(self):
        result = get_process_uptime()
        self.assertRegex(result, r"^\d+\.\d{3} seconds$")
        self.assertGreaterEqual(float(result.split()[0]), 0.0)

    def test_get_process_uptime_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_uptime"], get_process_uptime)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_process_uptime", names)

    def test_get_umask_returns_octal_value(self):
        result = get_umask()
        self.assertRegex(result, r"^0[0-7]{3}$")

    def test_get_umask_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_umask"], get_umask)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_umask", names)

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


class GetSystemBatteryStatusToolTests(unittest.TestCase):
    def test_get_system_battery_status_parses_android_dumpsys(self):
        completed = type(
            "Completed",
            (),
            {
                "stdout": (
                    "AC powered: false\\n"
                    "USB powered: true\\n"
                    "Wireless powered: false\\n"
                    "status: 2\\n"
                    "health: 2\\n"
                    "level: 87\\n"
                    "scale: 100\\n"
                    "voltage: 4191\\n"
                    "temperature: 253\\n"
                )
            },
        )()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed):
            result = get_system_battery_status()
        self.assertEqual(
            result,
            "Level: 87%\\n"
            "Status: Charging\\n"
            "Health: Good\\n"
            "Temperature: 25.3°C\\n"
            "Voltage: 4.191 V\\n"
            "Power source: USB",
        )

    def test_get_system_battery_status_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_system_battery_status"], get_system_battery_status)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_system_battery_status", names)


class GetSystemCpuUsageToolTests(unittest.TestCase):
    def test_get_system_cpu_usage_returns_percentage(self):
        completed = type("Completed", (), {"stdout": "CPU usage: 37.5%\n"})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed):
            result = get_system_cpu_usage()
        self.assertEqual(result, "37.50%")

    def test_get_system_cpu_usage_parses_android_top(self):
        completed = type(
            "Completed",
            (),
            {"stdout": "800%cpu   0%user   0%nice   0%sys 800%idle   0%iow   0%irq   0%sirq   0%host\n"},
        )()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed):
            result = get_system_cpu_usage()
        self.assertEqual(result, "0.00%")

    def test_get_system_cpu_usage_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_system_cpu_usage"], get_system_cpu_usage)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_system_cpu_usage", names)


class GetSystemMemoryUsageToolTests(unittest.TestCase):
    def test_get_system_memory_usage_returns_memory_values(self):
        result = get_system_memory_usage()
        self.assertRegex(result, r"^Total: \d+ bytes\nUsed: \d+ bytes\nAvailable: \d+ bytes$")
        values = [int(line.split()[1]) for line in result.splitlines()]
        self.assertEqual(len(values), 3)
        self.assertGreater(values[0], 0)
        self.assertGreaterEqual(values[1], 0)
        self.assertGreaterEqual(values[2], 0)
        self.assertLessEqual(values[1], values[0])
        self.assertLessEqual(values[2], values[0])

    def test_get_system_memory_usage_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_system_memory_usage"], get_system_memory_usage)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_system_memory_usage", names)


class GetSystemSwapUsageToolTests(unittest.TestCase):
    def test_get_system_swap_usage_returns_swap_values(self):
        result = get_system_swap_usage()
        self.assertRegex(result, r"^Total: \d+ bytes\nUsed: \d+ bytes\nFree: \d+ bytes$")
        values = [int(line.split()[1]) for line in result.splitlines()]
        self.assertEqual(len(values), 3)
        self.assertGreaterEqual(values[0], 0)
        self.assertGreaterEqual(values[1], 0)
        self.assertGreaterEqual(values[2], 0)
        self.assertLessEqual(values[1], values[0])
        self.assertLessEqual(values[2], values[0])

    def test_get_system_swap_usage_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_system_swap_usage"], get_system_swap_usage)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_system_swap_usage", names)


class GetSystemBootTimeToolTests(unittest.TestCase):
    def test_get_system_boot_time_returns_local_iso_datetime(self):
        result = get_system_boot_time()
        parsed = __import__("datetime").datetime.fromisoformat(result)
        self.assertIsNotNone(parsed.tzinfo)
        self.assertLessEqual(parsed.timestamp(), __import__("time").time())

    def test_get_system_boot_time_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_system_boot_time"], get_system_boot_time)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_system_boot_time", names)

if __name__ == "__main__":
    unittest.main()
