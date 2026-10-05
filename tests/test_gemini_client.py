"""Offline tests for the single-provider Cloudflare Nova client."""

import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from gemini_agent.client import GeminiClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class CloudflareClientTests(unittest.TestCase):
    def test_requires_cloudflare_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "CLOUDFLARE_API_TOKEN"):
                GeminiClient()

    def test_uses_cloudflare_only(self):
        with patch.dict(
            os.environ,
            {
                "CLOUDFLARE_API_TOKEN": "token",
                "CLOUDFLARE_ACCOUNT_ID": "account",
            },
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse({"choices": [{"message": {"content": "hello"}}]}),
        ) as open_url:
            answer = GeminiClient().ask("Hello")
        self.assertEqual(answer, "hello")
        self.assertEqual(open_url.call_count, 1)
        self.assertIn("/accounts/account/ai/v1/chat/completions", open_url.call_args.args[0].full_url)

    def test_uses_calculator_tool(self):
        tool_response = {
            "choices": [{
                "message": {
                    "content": "",
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "calculator",
                            "arguments": '{"expression":"17 * 23"}',
                        },
                    }],
                }
            }]
        }
        final_response = {"choices": [{"message": {"content": "391"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(tool_response), FakeResponse(final_response)],
        ) as open_url:
            client = GeminiClient()
            answer = client.ask("Use the calculator tool to calculate 17 * 23.")
        self.assertEqual(answer, "391")
        self.assertEqual(open_url.call_count, 2)
        self.assertEqual(
            client.last_tool_calls,
            [{"name": "calculator", "args": {"expression": "17 * 23"}, "result": "391", "expression": "17 * 23"}],
        )
        follow_up = json.loads(open_url.call_args_list[1].args[0].data)
        self.assertNotIn("tools", follow_up)
        self.assertNotIn("tool_choice", follow_up)

    def test_tool_calls_take_precedence_over_content(self):
        tool_response = {
            "choices": [{
                "message": {
                    "content": "remembered_fact",
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "remember_fact",
                            "arguments": '{"key":"favorite_color","value":"blue"}',
                        },
                    }],
                }
            }]
        }
        final_response = {"choices": [{"message": {"content": "Remembered favorite color."}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(tool_response), FakeResponse(final_response)],
        ):
            client = GeminiClient(
                tool_handlers={
                    "remember_fact": lambda key, value: f"Remembered {key} = {value}",
                }
            )
            answer = client.ask("Remember that my favorite color is blue.")
        self.assertEqual(answer, "Remembered favorite color.")
        self.assertEqual(client.last_tool_calls[0]["name"], "remember_fact")

    def test_content_form_tool_call_is_executed(self):
        tool_response = {
            "choices": [{
                "message": {
                    "content": 'remember_fact\n{"key":"favorite_color","value":"blue"}'
                }
            }]
        }
        final_response = {"choices": [{"message": {"content": "Remembered favorite color."}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(tool_response), FakeResponse(final_response)],
        ) as open_url:
            client = GeminiClient(
                tool_handlers={
                    "remember_fact": lambda key, value: f"Remembered {key} = {value}",
                }
            )
            answer = client.ask("Remember that my favorite color is blue.")
        self.assertEqual(answer, "Remembered favorite color.")
        self.assertEqual(client.last_tool_calls[0]["name"], "remember_fact")
        self.assertEqual(
            client.last_tool_calls[0]["args"],
            {"key": "favorite_color", "value": "blue"},
        )
        follow_up = json.loads(open_url.call_args_list[1].args[0].data)
        self.assertEqual(follow_up["messages"][-2]["role"], "assistant")
        self.assertEqual(follow_up["messages"][-1]["role"], "tool")

    def test_xml_content_form_tool_call_is_executed(self):
        tool_response = {
            "choices": [{
                "message": {
                    "content": '<tool_call>move_file<arg_key>path</arg_key><arg_value>test-write.txt</arg_value><arg_key>destination</arg_key><arg_value>moved-test-write.txt</arg_value></tool_call>'
                }
            }]
        }
        final_response = {"choices": [{"message": {"content": "Moved successfully."}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(tool_response), FakeResponse(final_response)],
        ):
            client = GeminiClient(
                tool_handlers={
                    "move_file": lambda path, destination: f"Moved {path} to {destination}",
                }
            )
            answer = client.ask("Use the move_file tool to move test-write.txt to moved-test-write.txt.")
        self.assertEqual(answer, "Moved successfully.")
        self.assertEqual(
            client.last_tool_calls[0]["args"],
            {"path": "test-write.txt", "destination": "moved-test-write.txt"},
        )

    def test_list_memory_tool_is_selected(self):
        response = {"choices": [{"message": {"content": "ok"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(response)) as open_url:
            GeminiClient().ask("Use the list_memory tool to tell me what you remember.")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual([t["function"]["name"] for t in sent["tools"]], ["list_memory"])
        self.assertEqual(sent["tool_choice"], {"type": "function", "function": {"name": "list_memory"}})

    def test_explicit_tool_is_selected(self):
        response = {"choices": [{"message": {"content": "ok"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(response)) as open_url:
            GeminiClient().ask("Use the delete_file tool to delete test.txt.")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual([t["function"]["name"] for t in sent["tools"]], ["delete_file"])
        self.assertEqual(sent["tool_choice"], {"type": "function", "function": {"name": "delete_file"}})

    def test_get_disk_usage_tool_is_selected(self):
        response = {"choices": [{"message": {"content": "ok"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(response)) as open_url:
            GeminiClient().ask("Use the get_disk_usage tool to inspect the current filesystem.")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual([t["function"]["name"] for t in sent["tools"]], ["get_disk_usage"])
        self.assertEqual(
            sent["tool_choice"],
            {"type": "function", "function": {"name": "get_disk_usage"}},
        )

    def test_get_system_info_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient()
            answer = client.ask("Use the get_system_info tool.")
        self.assertRegex(answer, r"^OS: .+\nArchitecture: .+\nPython: \d+\.\d+\.\d+$")
        self.assertEqual(open_url.call_count, 1)

    def test_get_process_id_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient()
            answer = client.ask("Use the get_process_id tool.")
        self.assertGreater(int(answer), 0)
        self.assertEqual(open_url.call_count, 1)

    def test_get_current_working_directory_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient()
            answer = client.ask("Use the get_current_working_directory tool.")
        self.assertTrue(answer)
        self.assertEqual(open_url.call_count, 1)

    def test_get_python_executable_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient()
            answer = client.ask("Use the get_python_executable tool.")
        self.assertTrue(answer)
        self.assertEqual(open_url.call_count, 1)

    def test_get_temp_directory_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient()
            answer = client.ask("Use the get_temp_directory tool.")
        self.assertTrue(answer)
        self.assertEqual(open_url.call_count, 1)

    def test_get_process_uptime_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient()
            answer = client.ask("Use the get_process_uptime tool.")
        self.assertRegex(answer, r"^\d+\.\d{3} seconds$")
        self.assertEqual(open_url.call_count, 1)

    def test_get_process_thread_count_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient()
            answer = client.ask("Use the get_process_thread_count tool.")
        self.assertGreater(int(answer), 0)
        self.assertEqual(open_url.call_count, 1)

    def test_get_user_id_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient()
            answer = client.ask("Use the get_user_id tool.")
        self.assertGreaterEqual(int(answer), 0)
        self.assertEqual(open_url.call_count, 1)

    def test_get_session_id_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient()
            answer = client.ask("Use the get_session_id tool.")
        self.assertGreater(int(answer), 0)
        self.assertEqual(open_url.call_count, 1)

    def test_get_process_group_id_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient()
            answer = client.ask("Use the get_process_group_id tool.")
        self.assertGreater(int(answer), 0)
        self.assertEqual(open_url.call_count, 1)

    def test_get_parent_process_id_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient()
            answer = client.ask("Use the get_parent_process_id tool.")
        self.assertGreater(int(answer), 0)
        self.assertEqual(open_url.call_count, 1)

    def test_list_processes_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(first_response),
        ) as open_url:
            answer = GeminiClient().ask("Use the list_processes tool.")
        self.assertTrue(answer)
        self.assertTrue(answer.splitlines()[0].split(maxsplit=1)[0].isdigit())
        self.assertEqual(open_url.call_count, 1)

    def test_run_command_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(first_response),
        ) as open_url:
            answer = GeminiClient().ask("Use the run_command tool to run `pwd`.")
        self.assertTrue(answer.startswith("Exit code: 0"))
        self.assertEqual(open_url.call_count, 1)

    def test_get_umask_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient()
            answer = client.ask("Use the get_umask tool.")
        self.assertRegex(answer, r"^0[0-7]{3}$")
        self.assertEqual(open_url.call_count, 1)

    def test_get_home_directory_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient()
            answer = client.ask("Use the get_home_directory tool.")
        self.assertEqual(answer, os.path.expanduser("~"))
        self.assertEqual(open_url.call_count, 1)

    def test_get_memory_usage_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient()
            answer = client.ask("Use the get_memory_usage tool.")
        self.assertGreater(int(answer), 0)
        self.assertEqual(open_url.call_count, 1)

    def test_get_cpu_count_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient()
            answer = client.ask("Use the get_cpu_count tool.")
        self.assertGreater(int(answer), 0)
        self.assertEqual(open_url.call_count, 1)

    def test_get_disk_usage_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient()
            answer = client.ask("Use the get_disk_usage tool to inspect the current filesystem.")
        self.assertRegex(
            answer,
            r"^Total: \d+ bytes\nUsed: \d+ bytes\nFree: \d+ bytes$",
        )
        self.assertEqual(open_url.call_count, 1)

    def test_get_file_info_tool_is_selected(self):
        response = {"choices": [{"message": {"content": "ok"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(response)) as open_url:
            GeminiClient().ask("Use the get_file_info tool to inspect notes.txt.")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual([t["function"]["name"] for t in sent["tools"]], ["get_file_info"])
        self.assertEqual(sent["tool_choice"], {"type": "function", "function": {"name": "get_file_info"}})

    def test_move_directory_tool_is_selected(self):
        response = {"choices": [{"message": {"content": "ok"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(response)) as open_url:
            GeminiClient().ask("Use the move_directory tool to move archive to moved/archive.")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual([t["function"]["name"] for t in sent["tools"]], ["move_directory"])
        self.assertEqual(sent["tool_choice"], {"type": "function", "function": {"name": "move_directory"}})

    def test_copy_directory_fallback_executes_when_cloudflare_returns_no_tool_call(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        final_response = {"choices": [{"message": {"content": "Copied successfully."}}]}
        calls = []

        def copy_directory(path, destination):
            calls.append((path, destination))
            return f"Copied directory {path} to {destination}"

        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(first_response), FakeResponse(final_response)],
        ):
            client = GeminiClient(tool_handlers={"copy_directory": copy_directory})
            answer = client.ask(
                "Use the copy_directory tool to copy copy-dir-test to copy-dir-test-copied."
            )

        self.assertEqual(answer, "Copied successfully.")
        self.assertEqual(calls, [("copy-dir-test", "copy-dir-test-copied")])
        self.assertEqual(client.last_tool_calls[0]["name"], "copy_directory")

    def test_copy_directory_explicit_request_overrides_wrong_native_arguments(self):
        first_response = {"choices": [{"message": {
            "content": None,
            "tool_calls": [{
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "copy_directory",
                    "arguments": {"path": ".", "destination": "copy-dir-test-copied"},
                },
            }],
        }}]}
        final_response = {"choices": [{"message": {"content": "Copied successfully."}}]}
        calls = []

        def copy_directory(path, destination):
            calls.append((path, destination))
            return f"Copied directory {path} to {destination}"

        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(first_response), FakeResponse(final_response)],
        ):
            client = GeminiClient(tool_handlers={"copy_directory": copy_directory})
            answer = client.ask(
                "Use the copy_directory tool to copy copy-dir-test to copy-dir-test-copied."
            )

        self.assertEqual(answer, "Copied successfully.")
        self.assertEqual(calls, [("copy-dir-test", "copy-dir-test-copied")])

    def test_copy_directory_tool_is_selected(self):
        response = {"choices": [{"message": {"content": "ok"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(response)) as open_url:
            GeminiClient().ask("Use the copy_directory tool to copy archive to copied/archive.")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual([t["function"]["name"] for t in sent["tools"]], ["copy_directory"])
        self.assertEqual(sent["tool_choice"], {"type": "function", "function": {"name": "copy_directory"}})

    def test_create_directory_alias_selects_make_directory(self):
        response = {"choices": [{"message": {"content": "ok"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(response)) as open_url:
            GeminiClient().ask("Use the create_directory tool to create archive-test/nested.")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual([t["function"]["name"] for t in sent["tools"]], ["make_directory"])
        self.assertEqual(sent["tool_choice"], {"type": "function", "function": {"name": "make_directory"}})

    def test_edit_text_file_alias_selects_edit_file(self):
        response = {"choices": [{"message": {"content": "ok"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(response)) as open_url:
            GeminiClient().ask("Use the edit_text_file tool to edit notes.txt.")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual([t["function"]["name"] for t in sent["tools"]], ["edit_file"])
        self.assertEqual(sent["tool_choice"], {"type": "function", "function": {"name": "edit_file"}})

    def test_delete_directory_alias_selects_remove_directory(self):
        response = {"choices": [{"message": {"content": "ok"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(response)) as open_url:
            GeminiClient().ask("Use the delete_directory tool to delete archive-test/nested.")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual([t["function"]["name"] for t in sent["tools"]], ["remove_directory"])
        self.assertEqual(sent["tool_choice"], {"type": "function", "function": {"name": "remove_directory"}})

    def test_read_text_file_alias_selects_read_file(self):
        response = {"choices": [{"message": {"content": "ok"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(response)) as open_url:
            GeminiClient().ask("Use the read_text_file tool to read README.md.")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual([t["function"]["name"] for t in sent["tools"]], ["read_file"])
        self.assertEqual(sent["tool_choice"], {"type": "function", "function": {"name": "read_file"}})

    def test_list_directory_recursive_explicit_selection(self):
        response = {"choices": [{"message": {"content": "ok"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(response)) as open_url:
            GeminiClient().ask("Use the list_directory_recursive tool to inspect the current directory.")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual([t["function"]["name"] for t in sent["tools"]], ["list_directory_recursive"])
        self.assertEqual(sent["tool_choice"], {"type": "function", "function": {"name": "list_directory_recursive"}})

    def test_filesystem_request_requires_tool(self):
        response = {"choices": [{"message": {"content": "ok"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(response)) as open_url:
            GeminiClient().ask("Please read this file.")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual(sent["tool_choice"], "required")

    def test_accepts_decoded_tool_arguments(self):
        tool_response = {
            "choices": [{
                "message": {
                    "content": "",
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "calculator",
                            "arguments": {"expression": "12 * 7"},
                        },
                    }],
                }
            }]
        }
        final_response = {"choices": [{"message": {"content": "84"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(tool_response), FakeResponse(final_response)],
        ):
            self.assertEqual(GeminiClient().ask("Calculate 12 * 7."), "84")

    def test_cloudflare_http_error(self):
        error = urllib.error.HTTPError(
            "https://example.test", 400, "bad request", {},
            io.BytesIO(b'{"error":{"message":"bad"}}'),
        )
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, r"Cloudflare API error \(400\)"):
                GeminiClient().ask("Hello")


if __name__ == "__main__":
    unittest.main()
