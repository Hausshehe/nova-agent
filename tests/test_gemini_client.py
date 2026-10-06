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

    def test_explicit_generated_capability_returns_after_one_execution(self):
        response = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "camera-call",
                        "type": "function",
                        "function": {
                            "name": "camera_shutter",
                            "arguments": "{}",
                        },
                    }]
                }
            }]
        }
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(response),
        ) as open_url:
            client = GeminiClient()
            client.tool_declarations.append({
                "name": "camera_shutter",
                "description": "Open the device camera.",
                "parameters": {"type": "OBJECT", "properties": {}},
            })
            client.tool_handlers["camera_shutter"] = lambda: "CAMERA OPENED"
            answer = client.ask("Use the camera_shutter capability to open the device camera.")
        self.assertEqual(answer, "CAMERA OPENED")
        self.assertEqual(open_url.call_count, 1)

    def test_unnamed_newly_generated_capability_routes_to_generated_wrapper(self):
        response = {
            "choices": [{"message": {"tool_calls": [{
                "id": "generated-call",
                "type": "function",
                "function": {"name": "camera_shutter", "arguments": "{}"},
            }]}}]
        }

        def generated_camera_capability():
            if False:
                return _run_android_mechanism_extension
            return "CAMERA OPENED"

        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen", return_value=FakeResponse(response)
        ) as open_url, patch.dict(
            "gemini_agent.client.TOOL_HANDLERS",
            {"camera_shutter": generated_camera_capability},
        ):
            client = GeminiClient()
            client.tool_declarations.append({
                "name": "camera_shutter",
                "description": "Open the device camera.",
                "parameters": {"type": "OBJECT", "properties": {}},
            })
            answer = client.ask(
                "Use the newly generated camera-opening capability to open the device camera."
            )

        self.assertEqual(answer, "CAMERA OPENED")
        self.assertEqual(client.last_tool_calls[0]["name"], "camera_shutter")
        self.assertEqual(open_url.call_count, 1)

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


    def test_foreground_android_component_routes_without_cloudflare(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen") as open_url:
            client = GeminiClient()
            client.tool_handlers["get_foreground_android_component"] = lambda: (
                "Foreground Android component inspection (read-only): "
                "ResumedActivity: com.termux/.app.TermuxActivity"
            )
            answer = client.ask("Inspect the current foreground Android component without interacting with it.")
        self.assertIn("com.termux/.app.TermuxActivity", answer)
        open_url.assert_not_called()

    def test_inspect_android_ui_routes_without_cloudflare(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen") as open_url:
            client = GeminiClient()
            seen = []
            client.tool_handlers["inspect_android_ui"] = lambda selector="": (
                seen.append(selector) or "Android UI inspection (read-only): <node text='CTRL'/>"
            )
            answer = client.ask(
                "Use the Android UI inspection tool with selector ui-text:CTRL. "
                "Inspect read-only and do not interact with the UI."
            )
        self.assertIn("Android UI inspection", answer)
        self.assertEqual(seen, ["ui-text:CTRL"])
        open_url.assert_not_called()

    def test_discover_android_ui_actions_routes_without_cloudflare(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen") as open_url:
            client = GeminiClient()
            client.tool_handlers["discover_android_ui_actions"] = lambda: (
                "Android UI action discovery (read-only): Clickable enabled controls found: 0"
            )
            answer = client.ask(
                "Discover the clickable Android UI controls currently available without interacting with the device, and report them."
            )
        self.assertIn("Clickable enabled controls found: 0", answer)
        open_url.assert_not_called()


    def test_validate_android_mechanism_routes_without_cloudflare(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen") as open_url:
            client = GeminiClient()
            client.tool_handlers["validate_android_mechanism"] = (
                lambda request, mechanism: f"validated {request} via {mechanism}"
            )
            answer = client.ask(
                "Validate the Android mechanism: intent:android.media.action.IMAGE_CAPTURE "
                "for the capability capture a photo."
            )
        self.assertIn("validated", answer)
        self.assertIn("intent:android.media.action.IMAGE_CAPTURE", answer)
        open_url.assert_not_called()

    def test_execute_validated_android_mechanism_routes_without_cloudflare(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen") as open_url:
            client = GeminiClient()
            client.tool_handlers["execute_validated_android_mechanism"] = (
                lambda request, mechanism: f"executed {request} via {mechanism}"
            )
            answer = client.ask(
                "Execute the validated Android mechanism: intent:android.media.action.IMAGE_CAPTURE "
                "for the capability capture a photo."
            )
        self.assertIn("executed", answer)
        self.assertIn("intent:android.media.action.IMAGE_CAPTURE", answer)
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

    def test_compound_self_extension_request_uses_extension_transaction(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse({"choices": [{"message": {"content": "ok"}}]}),
        ) as open_url, patch(
            "gemini_agent.client.GeminiClient._extension_inspection_context",
            return_value="inspection context",
        ):
            client = GeminiClient()
            answer = client.ask(
                "Add a capability to open the device camera. "
                "You do not currently have this capability. "
                "Discover the Android mechanism, validate it, extend yourself using that mechanism, "
                "test the extension, and report exactly what happened."
            )
        self.assertEqual(answer, "ok")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual(sent["tool_choice"]["function"]["name"], "apply_capability_extension")
        self.assertEqual(
            [tool["function"]["name"] for tool in sent["tools"]],
            ["apply_capability_extension"],
        )

    def test_android_mechanism_extension_normalizes_spaced_target(self):
        tool_response = {
            "choices": [{"message": {"content": "", "tool_calls": [{
                "id": "call-extension",
                "type": "function",
                "function": {
                    "name": "apply_capability_extension",
                    "arguments": json.dumps({
                        "request": "open the device camera",
                        "implementation_kind": "android_mechanism",
                        "implementation_target": "intent: android.media.action.IMAGE_CAPTURE",
                        "implementation_args": "{}",
                        "path": "gemini_agent/tools.py",
                        "declaration_description": "Open the device camera.",
                    }),
                },
            }]}}]
        }
        seen = []
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
                    "apply_capability_extension": lambda **kwargs: seen.append(kwargs) or "extension result"
                }
            )
            answer = client.ask("Add a capability to open the device camera and extend yourself using the discovered Android mechanism.")
        self.assertEqual(answer, "extension result")
        self.assertEqual(seen[0]["implementation_target"], "intent:android.media.action.IMAGE_CAPTURE")
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