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

    def test_intent_routing_narrows_unambiguous_capability_set(self):
        response = {"choices": [{"message": {"content": "ok"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(response),
        ) as open_url:
            GeminiClient().ask("What is the current battery level?")
        sent = json.loads(open_url.call_args.args[0].data)
        names = [tool["function"]["name"] for tool in sent["tools"]]
        self.assertEqual(names, ["get_system_battery_status"])

    def test_intent_routing_keeps_multiple_needed_capabilities(self):
        response = {"choices": [{"message": {"content": "ok"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(response),
        ) as open_url:
            GeminiClient().ask("Calculate 17 * 23, then get the current date and time.")
        sent = json.loads(open_url.call_args.args[0].data)
        names = [tool["function"]["name"] for tool in sent["tools"]]
        self.assertEqual(names, ["calculator", "current_datetime"])

    def test_natural_capability_gap_request_uses_gap_tool(self):
        tool_response = {
            "choices": [{"message": {"content": "", "tool_calls": [{
                "id": "call-gap",
                "type": "function",
                "function": {
                    "name": "assess_capability_gap",
                    "arguments": '{"request":"control the phone camera"}',
                },
            }]}}]
        }
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(tool_response),
        ) as open_url:
            client = GeminiClient()
            answer = client.ask("Do I have a capability to control the phone camera?")
        self.assertIn("Capability gap:", answer)
        self.assertEqual(client.last_tool_calls[0]["name"], "assess_capability_gap")
        self.assertEqual(open_url.call_count, 1)

    def test_natural_extension_request_uses_extension_planner(self):
        tool_response = {
            "choices": [{"message": {"content": "", "tool_calls": [{
                "id": "call-extension",
                "type": "function",
                "function": {
                    "name": "plan_capability_extension",
                    "arguments": '{"request":"control the phone camera shutter"}',
                },
            }]}}]
        }
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(tool_response),
        ) as open_url:
            client = GeminiClient()
            answer = client.ask("How would you add this capability: control the phone camera shutter?")
        self.assertIn("Extension plan: capability is missing.", answer)
        self.assertIn("extend_camera_shutter", answer)
        self.assertEqual(client.last_tool_calls[0]["name"], "plan_capability_extension")
        self.assertEqual(open_url.call_count, 1)

    def test_natural_extension_application_retries_after_failed_edit(self):
        apply_response = {
            "choices": [{"message": {"content": "", "tool_calls": [{
                "id": "call-apply-extension",
                "type": "function",
                "function": {
                    "name": "apply_capability_extension",
                    "arguments": '{"request":"control the phone camera shutter","path":"gemini_agent/tools.py","old_text":"VALUE = 1","new_text":"VALUE = 2"}',
                },
            }]}}]
        }
        failure = (
            "Extension not applied: proposed source is invalid Python: "
            "closing parenthesis does not match opening parenthesis."
        )
        success = (
            "Edited gemini_agent/tools.py\\n"
            "Extension status: source edit applied and transaction committed."
        )
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(apply_response), FakeResponse(apply_response)],
        ) as open_url, patch.dict(
            "gemini_agent.client.TOOL_HANDLERS",
            {"apply_capability_extension": lambda **kwargs: failure if kwargs["new_text"] == "VALUE = 2" else success},
        ):
            client = GeminiClient()
            # The first model proposal fails; the second proposal is accepted.
            def handler(**kwargs):
                return failure if kwargs["new_text"] == "VALUE = 2" else success
            client.tool_handlers["apply_capability_extension"] = handler
            answer = client.ask("Apply the capability extension for the phone camera shutter.")
        self.assertIn("Extension status: source edit applied and transaction committed.", answer)
        self.assertEqual(
            [trace["name"] for trace in client.last_tool_calls],
            ["apply_capability_extension", "apply_capability_extension"],
        )
        self.assertEqual(open_url.call_count, 2)
        second_payload = json.loads(open_url.call_args_list[1].args[0].data)
        self.assertEqual(
            second_payload["tool_choice"],
            {"type": "function", "function": {"name": "apply_capability_extension"}},
        )
        self.assertIn(
            "Extension not applied: proposed source is invalid Python",
            second_payload["messages"][-1]["content"],
        )

    def test_natural_capability_request_uses_capability_inventory(self):
        tool_response = {
            "choices": [{"message": {"content": "", "tool_calls": [{
                "id": "call-capabilities",
                "type": "function",
                "function": {"name": "capability_inventory", "arguments": "{}"},
            }]}}]
        }
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(tool_response),
        ) as open_url:
            client = GeminiClient()
            answer = client.ask("List Nova's capabilities and what each tool does.")
        self.assertIn("Capabilities (", answer)
        self.assertIn("- calculator: Calculate basic arithmetic expressions.", answer)
        self.assertEqual(open_url.call_count, 1)
        self.assertEqual(client.last_tool_calls[0]["name"], "capability_inventory")

    def test_natural_self_test_request_uses_self_test_tool(self):
        tool_response = {
            "choices": [{"message": {"content": "", "tool_calls": [{
                "id": "call-self-test",
                "type": "function",
                "function": {"name": "self_test", "arguments": "{}"},
            }]}}]
        }
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(tool_response),
        ) as open_url:
            client = GeminiClient()
            answer = client.ask("Run the self-test and report whether Nova's local execution substrate is healthy.")
        self.assertEqual(answer, "Self-test: PASS (5/5 checks passed)")
        self.assertEqual(open_url.call_count, 1)
        self.assertEqual(client.last_tool_calls[0]["name"], "self_test")

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

    def test_tool_calls_can_compose_multiple_steps(self):
        first_response = {
            "choices": [{
                "message": {
                    "content": "",
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "calculator",
                            "arguments": '{"expression":"2 + 3"}',
                        },
                    }],
                }
            }]
        }
        second_response = {
            "choices": [{
                "message": {
                    "content": "",
                    "tool_calls": [{
                        "id": "call-2",
                        "type": "function",
                        "function": {
                            "name": "current_datetime",
                            "arguments": "{}",
                        },
                    }],
                }
            }]
        }
        final_response = {"choices": [{"message": {"content": "5 and the current time."}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[
                FakeResponse(first_response),
                FakeResponse(second_response),
                FakeResponse(final_response),
            ],
        ) as open_url:
            client = GeminiClient()
            answer = client.ask("Perform the task using the available tools and report the result.")
        self.assertEqual(answer, "5 and the current time.")
        self.assertEqual(open_url.call_count, 3)
        self.assertEqual([call["name"] for call in client.last_tool_calls], ["calculator", "current_datetime"])
        second_payload = json.loads(open_url.call_args_list[1].args[0].data)
        self.assertIn("tools", second_payload)
        self.assertEqual(second_payload["tool_choice"], "auto")

    def test_content_tool_call_arguments_are_normalized_for_composition(self):
        first_response = {
            "choices": [{
                "message": {
                    "content": "<tool_call>\ncurrent_datetime\n</tool_call>",
                }
            }]
        }
        final_response = {"choices": [{"message": {"content": "done"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(first_response), FakeResponse(final_response)],
        ) as open_url:
            client = GeminiClient()
            answer = client.ask("Perform the task using the available tools and report the result.")
        self.assertEqual(answer, "done")
        self.assertEqual(open_url.call_count, 2)
        follow_up = json.loads(open_url.call_args_list[1].args[0].data)
        tool_call = follow_up["messages"][-2]["tool_calls"][0]
        self.assertEqual(tool_call["type"], "function")
        self.assertEqual(tool_call["function"]["arguments"], "{}")

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



    def test_get_system_boot_time_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient()
            answer = client.ask("Use the get_system_boot_time tool.")
        self.assertRegex(answer, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")
        self.assertEqual(open_url.call_count, 1)

    def test_get_system_cpu_usage_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient(tool_handlers={"get_system_cpu_usage": lambda: "37.50%"})
            answer = client.ask("Use the get_system_cpu_usage tool.")
        self.assertRegex(answer, r"^\d+\.\d{2}%$")
        self.assertEqual(open_url.call_count, 1)

    def test_get_screen_state_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        screen = "Screen: ON"
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient(tool_handlers={"get_screen_state": lambda: screen})
            answer = client.ask("Use the get_screen_state tool to show the current screen state.")
        self.assertEqual(answer, screen)
        self.assertEqual(open_url.call_count, 1)

    def test_get_screen_brightness_mode_explicit_request_does_not_match_brightness(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        mode = "Brightness mode: Automatic"
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient(tool_handlers={"get_screen_brightness_mode": lambda: mode})
            answer = client.ask("Use the get_screen_brightness_mode tool to show Nova's current screen brightness mode.")
        self.assertEqual(answer, mode)
        self.assertEqual(open_url.call_count, 1)

    def test_get_screen_brightness_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        brightness = "Brightness: 50% (128/255)"
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient(tool_handlers={"get_screen_brightness": lambda: brightness})
            answer = client.ask("Use the get_screen_brightness tool to show the current screen brightness.")
        self.assertEqual(answer, brightness)
        self.assertEqual(open_url.call_count, 1)

    def test_get_system_battery_status_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        battery = (
            "Level: 87%\\n"
            "Status: Charging\\n"
            "Health: Good\\n"
            "Temperature: 25.3°C\\n"
            "Voltage: 4.191 V\\n"
            "Power source: USB"
        )
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient(tool_handlers={"get_system_battery_status": lambda: battery})
            answer = client.ask("Use the get_system_battery_status tool.")
        self.assertEqual(answer, battery)
        self.assertEqual(open_url.call_count, 1)


    def test_get_system_swap_usage_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(first_response)) as open_url:
            client = GeminiClient()
            answer = client.ask("Use the get_system_swap_usage tool.")
        self.assertRegex(answer, r"^Total: \d+ bytes\nUsed: \d+ bytes\nFree: \d+ bytes$")
        self.assertEqual(open_url.call_count, 1)

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

    def test_get_process_status_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(first_response),
        ) as open_url:
            answer = GeminiClient().ask(
                f"Use the get_process_status tool for pid {os.getpid()}."
            )
        self.assertIn(f"PID: {os.getpid()}", answer)
        self.assertEqual(open_url.call_count, 1)

    def test_get_process_executable_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(first_response),
        ) as open_url:
            answer = GeminiClient().ask(
                f"Use the get_process_executable tool for pid {os.getpid()}."
            )
        self.assertTrue(answer)
        self.assertIn("python", answer.lower())