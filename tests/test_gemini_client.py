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

    def test_intent_routing_selects_android_mechanism_discovery(self):
        response = {"choices": [{"message": {"content": "ok"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(response),
        ) as open_url:
            GeminiClient().ask("Discover Android mechanisms for controlling the camera.")
        sent = json.loads(open_url.call_args.args[0].data)
        names = [tool["function"]["name"] for tool in sent["tools"]]
        self.assertEqual(names, ["discover_android_mechanisms"])


    def test_inspect_android_ui_routes_without_cloudflare(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen") as open_url:
            client = GeminiClient()
            client.tool_handlers["inspect_android_ui"] = lambda: (
                "Android UI inspection (read-only): <hierarchy/>"
            )
            answer = client.ask("Inspect the current Android UI without interacting with it.")
        self.assertIn("Android UI inspection", answer)
        open_url.assert_not_called()

    def test_resolve_android_intent_uses_prompt_action_deterministically(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
        ) as open_url:
            client = GeminiClient()
            client.tool_handlers["resolve_android_intent"] = lambda action: (
                "Android intent resolution (read-only): android.media.action.IMAGE_CAPTURE\\n"
                "com.transsion.camera/.app.CaptureActivity\\n"
                "Intent was resolved only; it was not launched and no device state was modified."
            )
            answer = client.ask(
                "Resolve the Android IMAGE_CAPTURE intent handler without launching the intent, and report the result."
            )
        self.assertIn("IMAGE_CAPTURE", answer)
        open_url.assert_not_called()


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

    def test_natural_android_key_event_request_uses_local_action_tool(self):
        tool_response = {
            "choices": [{"message": {"content": "", "tool_calls": [{
                "id": "call-keyevent",
                "type": "function",
                "function": {
                    "name": "send_android_keyevent",
                    "arguments": '{"keycode":"CAMERA"}',
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
        ) as open_url, patch(
            "gemini_agent.client.TOOL_HANDLERS",
            {"send_android_keyevent": lambda keycode: f"Android key event {keycode} sent."},
        ):
            client = GeminiClient()
            answer = client.ask("Use the Android key event tool with CAMERA.")
        self.assertIn("Android key event CAMERA sent.", answer)
        self.assertEqual(client.last_tool_calls[0]["name"], "send_android_keyevent")
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
        self.assertIn("Proposed tool: extend_camera_shutter", answer)
        self.assertIn("extend_camera_shutter", answer)
        self.assertEqual(client.last_tool_calls[0]["name"], "plan_capability_extension")
        self.assertEqual(open_url.call_count, 1)

    def test_natural_extension_application_uses_local_inspection_then_applies(self):
        tool_response = {
            "choices": [{"message": {"content": "", "tool_calls": [{
                "id": "call-extension",
                "type": "function",
                "function": {
                    "name": "apply_capability_extension",
                    "arguments": json.dumps({
                        "request": "control the phone camera shutter",
                        "path": "gemini_agent/tools.py",
                        "function_source": "def camera_shutter():\n    return \"ok\"",
                        "declaration_description": "Take a photo with the phone camera.",
                    }),
                },
            }]}}]
        }
        success = "Edited gemini_agent/tools.py\\nExtension status: source edit applied and transaction committed."
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(tool_response),
        ) as open_url, patch.dict(
            "gemini_agent.client.TOOL_HANDLERS",
            {"apply_capability_extension": lambda **kwargs: success},
        ):
            client = GeminiClient()
            answer = client.ask("Apply the capability extension for the phone camera shutter.")
        self.assertIn("Extension status: source edit applied and transaction committed.", answer)
        self.assertEqual(client.last_tool_calls[0]["name"], "apply_capability_extension")
        self.assertEqual(open_url.call_count, 1)
        payload = json.loads(open_url.call_args.args[0].data.decode())
        self.assertEqual(payload["tool_choice"]["function"]["name"], "apply_capability_extension")
        self.assertEqual(payload["tools"][0]["function"]["name"], "apply_capability_extension")
        inspection = payload["messages"][0]["content"]
        self.assertIn("Repository inspection was performed locally", inspection)
        self.assertIn("def apply_capability_extension", inspection)
        self.assertIn("gemini_agent/tools.py", inspection)
        self.assertIn("HARD CONSTRAINT: the proposed capability name is exactly 'camera_shutter'.", inspection)
        self.assertIn("HARD CONSTRAINT: the proposed capability name is exactly 'camera_shutter'.", inspection)

    def test_extension_request_filler_uses_latest_user_request(self):
        args = {
            "path": "gemini_agent/tools.py",
            "old_text": "VALUE = 1",
            "new_text": "VALUE = 2",
        }
        filled = GeminiClient._fill_extension_request(
            args,
            "Apply a capability extension for the phone camera shutter.",
        )
        self.assertEqual(
            filled["request"],
            "Apply a capability extension for the phone camera shutter.",
        )
        self.assertEqual(filled["path"], "gemini_agent/tools.py")
        self.assertEqual(filled["old_text"], "VALUE = 1")
        self.assertEqual(filled["new_text"], "VALUE = 2")

    def test_natural_extension_application_returns_first_transaction_result(self):
        tool_response = {
            "choices": [{"message": {"content": "", "tool_calls": [{
                "id": "call-extension",
                "type": "function",
                "function": {
                    "name": "apply_capability_extension",
                    "arguments": json.dumps({
                        "request": "control the phone camera shutter",
                        "path": "gemini_agent/tools.py",
                        "old_text": "VALUE = 1",
                        "new_text": "VALUE = 2",
                    }),
                },
            }]}}]
        }
        failure = "Extension not applied: proposed source is invalid Python."
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(tool_response),
        ) as open_url:
            client = GeminiClient(
                tool_handlers={"apply_capability_extension": lambda **kwargs: failure}
            )
            answer = client.ask("Apply the capability extension for the phone camera shutter.")
        self.assertEqual(answer, failure)
        self.assertEqual(len(client.last_tool_calls), 1)
        self.assertEqual(open_url.call_count, 1)

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

    def test_natural_camera_discovery_request_uses_discovery_tool(self):
        tool_response = {
            "choices": [{"message": {"content": "", "tool_calls": [{
                "id": "call-camera-discovery",
                "type": "function",
                "function": {"name": "discover_camera_control", "arguments": "{}"},
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
            client = GeminiClient(
                tool_handlers={
                    "discover_camera_control": lambda: "Camera control environment discovery (read-only): test"
                }
            )
            answer = client.ask("Discover the phone camera control environment.")
        self.assertIn("Camera control environment discovery (read-only): test", answer)
        self.assertEqual(open_url.call_count, 1)
        self.assertEqual(client.last_tool_calls[0]["name"], "discover_camera_control")

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
        self.assertEqual(open_url.call_count, 1)

    def test_get_process_working_directory_explicit_request_returns_local_result(self):
        first_response = {"choices": [{"message": {"content": None, "tool_calls": []}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(first_response),
        ) as open_url:
            client = GeminiClient()
            answer = client.ask(
                f"Use the get_process_working_directory tool for pid {os.getpid()}."
            )
        self.assertEqual(answer, os.getcwd())
        self.assertEqual(open_url.call_count, 1)

    def test_get_process_command_line_explicit_request_returns_local_result(self):
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
                f"Use the get_process_command_line tool for pid {os.getpid()}."
            )
        self.assertTrue(answer)
        self.assertIn("python", answer.lower())
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
