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


class RawResponse:
    def __init__(self, payload):
        self.payload = payload

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

    def test_whitespace_only_tool_arguments_are_treated_as_empty(self):
        self.assertEqual(GeminiClient._parse_tool_arguments("   \n\t"), {})

    def test_outcome_ledger_request_uses_local_persistence_and_retrieval(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen") as open_url:
            client = GeminiClient()
            recorded = []
            def record_capability_outcome(capability, stage, status, evidence):
                recorded.append((capability, stage, status, evidence))
                return "Capability outcome recorded: ledger_probe"
            def get_capability_outcome_history(capability, limit=20):
                return "Capability outcome history: ledger_probe\\nEntries: 1\\nRecorded at: 2026-10-06T20:03:00+00:00"
            client.tool_handlers["record_capability_outcome"] = record_capability_outcome
            client.tool_handlers["get_capability_outcome_history"] = get_capability_outcome_history
            answer = client.ask(
                'Record a verified outcome in Nova\'s capability outcome ledger for capability '
                '"ledger_probe" at stage "verification" with status "VERIFIED" and evidence '
                '"bounded real-world ledger test". Then read back the most recent outcome history '
                'for "ledger_probe".'
            )
        self.assertIn("Recorded at: 2026-10-06T20:03:00+00:00", answer)
        self.assertEqual(
            recorded,
            [("ledger_probe", "verification", "VERIFIED", "bounded real-world ledger test")],
        )
        self.assertEqual(client.last_tool_calls[0]["args"]["capability"], "ledger_probe")
        self.assertEqual([call["name"] for call in client.last_tool_calls], [
            "record_capability_outcome",
            "get_capability_outcome_history",
        ])
        open_url.assert_not_called()

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

    def test_named_generated_capability_routes_without_cloudflare_argument_generation(self):
        def generated_probe():
            return "REPAIRED"

        generated_probe.__nova_generated_capability__ = True
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch.dict(
            "gemini_agent.client.TOOL_HANDLERS",
            {"generated_probe": generated_probe},
            clear=False,
        ):
            client = GeminiClient()
            client.tool_handlers["generated_probe"] = generated_probe
            with patch("urllib.request.urlopen") as open_url:
                answer = client.ask(
                    "Independently execute the repaired generated_probe capability exactly once."
                )
        self.assertEqual(answer, "REPAIRED")
        open_url.assert_not_called()

    def test_explicit_recover_command_preserves_expected_postcondition(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ):
            client = GeminiClient()
            from unittest.mock import Mock
            recover = Mock(return_value="Outcome: VERIFIED")
            with patch.dict(client.tool_handlers, {"recover_command": recover}), patch.object(
                client, "_requested_local_tool", return_value="recover_command"
            ):
                answer = client.ask(
                    "Use recover_command to run `python --version`. "
                    "The expected postcondition is exactly `Python`. "
                    "You must pass `Python` as the recover_command expected argument."
                )
        self.assertEqual(answer, "Outcome: VERIFIED")
        recover.assert_called_once_with(command="python --version", expected="Python")
        self.assertEqual(client.last_tool_calls[-1]["args"], {
            "command": "python --version",
            "expected": "Python",
        })
    def test_explicit_android_recovery_routes_with_supplied_verification(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ):
            client = GeminiClient()
            from unittest.mock import Mock
            recover = Mock(return_value="Replan: selected alternate viable mechanism.")
            client.tool_handlers["recover_android_mechanism"] = recover
            answer = client.ask(
                "Use recover_android_mechanism for the Android mechanism ui-text:CTRL. "
                "Treat the supplied post-action verification as genuinely FAILED for this test: "
                "FAILED: bounded verification proved the goal was not achieved. "
                "The request goal is: activate a visible clickable Android UI control."
            )
        self.assertEqual(answer, "Replan: selected alternate viable mechanism.")
        recover.assert_called_once()
        args = recover.call_args.kwargs
        self.assertEqual(args["mechanism"], "ui-text:CTRL")
        self.assertIn("FAILED: bounded verification proved the goal was not achieved.", args["verification"])
        self.assertEqual(client.last_tool_calls[-1]["name"], "recover_android_mechanism")

    def test_requested_local_tool_resolves_unnamed_newly_generated_capability(self):
        def generated_camera_capability():
            return "CAMERA OPENED"

        generated_camera_capability.__nova_generated_capability__ = True

        contents = [{
            "role": "user",
            "parts": [{
                "text": (
                    "Use the newly generated camera-opening capability to open "
                    "the device camera."
                )
            }],
        }]
        with patch.dict(
            "gemini_agent.client.TOOL_HANDLERS",
            {"camera_shutter": generated_camera_capability},
            clear=True,
        ):
            selected = GeminiClient._requested_local_tool(contents)

        self.assertEqual(selected, "camera_shutter")

    def test_unnamed_newly_generated_capability_routes_to_generated_wrapper(self):
        def generated_camera_capability():
            return "CAMERA OPENED"

        generated_camera_capability.__nova_generated_capability__ = True

        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen"
        ) as open_url, patch.dict(
            "gemini_agent.client.TOOL_HANDLERS",
            {"camera_shutter": generated_camera_capability},
            clear=True,
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
        self.assertEqual(open_url.call_count, 0)

    def test_retries_transient_invalid_cloudflare_json_response(self):
        valid = {"choices": [{"message": {"content": "hello after retry"}}]}
        with patch.dict(
            os.environ,
            {
                "CLOUDFLARE_API_TOKEN": "token",
                "CLOUDFLARE_ACCOUNT_ID": "account",
            },
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[RawResponse(b"   \n"), FakeResponse(valid)],
        ) as open_url:
            answer = GeminiClient().ask("Hello")
        self.assertEqual(answer, "hello after retry")
        self.assertEqual(open_url.call_count, 2)

    def test_normal_decision_policy_exposes_verified_experience_selection(self):
        response = {"choices": [{"message": {"content": "selected"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(response),
        ) as open_url:
            GeminiClient().ask(
                'Choose between strategy "fallback_probe" and strategy "retry_safe" '
                'for recovering a failed network check.'
            )
        sent = json.loads(open_url.call_args.args[0].data)
        system_messages = [
            message["content"]
            for message in sent["messages"]
            if message.get("role") == "system"
        ]
        self.assertTrue(system_messages)
        self.assertIn("verified-experience preference supplied by Nova", system_messages[0])
        self.assertIn("Treat learned experience only as a preference", system_messages[0])

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


    def test_named_generated_capability_executes_locally_without_cloudflare(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen") as open_url:
            client = GeminiClient()
            def repaired_capability():
                return "REPAIRED CAPABILITY RESULT"
            repaired_capability.__nova_generated_capability__ = True
            client.tool_handlers["camera_shutter"] = repaired_capability
            answer = client.ask(
                "Independently verify the repaired camera_shutter capability now. "
                "Execute the repaired capability exactly once and report the result."
            )
        self.assertEqual(answer, "REPAIRED CAPABILITY RESULT")
        self.assertEqual(client.last_tool_calls[0]["name"], "camera_shutter")
        open_url.assert_not_called()


    def test_verified_generated_capability_records_verification_without_accepting(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen") as open_url:
            client = GeminiClient()
            def repaired_capability():
                return "Android mechanism execution:\nPost-action verification: VERIFIED: expected component is foreground."
            repaired_capability.__nova_generated_capability__ = True
            recorded = []
            def record_verification(capability, verification):
                recorded.append((capability, verification))
                return "Repair verification recorded: camera_shutter"
            client.tool_handlers["camera_shutter"] = repaired_capability
            client.tool_handlers["record_capability_repair_verification"] = record_verification
            client.tool_handlers["accept_verified_capability_repair"] = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("acceptance must not occur during execution"))
            answer = client.ask("Independently verify the repaired camera_shutter capability now. Execute the repaired capability exactly once and report the result.")
        self.assertIn("Post-action verification: VERIFIED", answer)
        self.assertIn("Repair verification recorded: camera_shutter", answer)
        self.assertEqual(recorded[0][0], "camera_shutter")
        self.assertIn("Post-action verification: VERIFIED", recorded[0][1])
        open_url.assert_not_called()

    def test_repair_acceptance_does_not_execute_generated_capability(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen") as open_url:
            client = GeminiClient()
            executed = []
            def repaired_capability():
                executed.append(True)
                return "MUST NOT EXECUTE"
            repaired_capability.__nova_generated_capability__ = True
            client.tool_handlers["camera_shutter"] = repaired_capability
            client.tool_handlers["accept_verified_capability_repair"] = lambda capability, verification="": f"accepted {capability}"
            answer = client.ask("Accept the repaired camera_shutter capability only if its most recent independent real-world verification is explicitly VERIFIED. Do not execute camera_shutter again.")
        self.assertEqual(answer, "accepted camera_shutter")
        self.assertEqual(executed, [])
        open_url.assert_not_called()
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

    def test_android_mechanism_execution_routes_through_generic_dispatcher(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ):
            client = GeminiClient(
                tool_handlers={
                    "discover_android_mechanisms": lambda request: "intent:android.media.action.IMAGE_CAPTURE",
                    "validate_android_mechanism": lambda request, mechanism: "Status: VIABLE",
                    "execute_android_mechanism": lambda request, mechanism: f"executed {mechanism}",
                }
            )
            answer = client.ask(
                "Use the Android mechanism execution capability. Discover, validate, select, and execute a viable mechanism."
            )
        self.assertEqual(answer, "executed intent:android.media.action.IMAGE_CAPTURE")

    def test_android_mechanism_execution_selects_discovered_ui_text_mechanism(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ):
            client = GeminiClient(
                tool_handlers={
                    "discover_android_mechanisms": lambda request: (
                        "Android mechanism discovery (read-only):\n"
                        "Discovered bounded UI mechanisms:\n"
                        "ui-text:Take Photo"
                    ),
                    "validate_android_mechanism": lambda request, mechanism: "Status: VIABLE",
                    "execute_android_mechanism": lambda request, mechanism: f"executed {mechanism}",
                }
            )
            answer = client.ask(
                "Use the Android mechanism execution capability to activate the visible "
                "Take Photo control. Discover the mechanism yourself and execute it."
            )
        self.assertIn("executed ui-text:Take Photo", answer)


    def test_android_mechanism_execution_capability_selects_discovered_viable_mechanism(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen") as open_url:
            client = GeminiClient()
            client.tool_handlers["discover_android_mechanisms"] = lambda request: (
                "Android mechanism discovery (read-only):\n"
                "Discovered bounded intent mechanisms:\n"
                "intent:android.media.action.IMAGE_CAPTURE\n"
                "intent:android.media.action.STILL_IMAGE_CAMERA"
            )
            client.tool_handlers["validate_android_mechanism"] = (
                lambda request, mechanism: f"Status: VIABLE\nMechanism: {mechanism}"
            )
            client.tool_handlers["execute_android_mechanism"] = (
                lambda request, mechanism: f"executed via {mechanism}"
            )
            answer = client.ask(
                "Use the Android mechanism execution capability to open the device camera. "
                "Before executing, choose a viable mechanism."
            )
        self.assertIn("executed via intent:android.media.action.IMAGE_CAPTURE", answer)
        open_url.assert_not_called()

    def test_execute_validated_android_mechanism_routes_without_cloudflare(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen") as open_url:
            client = GeminiClient()
            client.tool_handlers["execute_android_mechanism"] = (
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

    def test_explicit_capability_history_analysis_is_local_and_read_only(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "gemini_agent.client.analyze_capability_history",
            return_value="Repair decision: ACCEPT_ELIGIBLE",
        ) as analyzer, patch("urllib.request.urlopen") as open_url:
            client = GeminiClient()
            result = client.ask(
                "Analyze persisted capability history for capability \"generated_probe\" "
                "and report the repair verification decision. Do not execute any capability "
                "or modify anything."
            )
        self.assertEqual(result, "Repair decision: ACCEPT_ELIGIBLE")
        analyzer.assert_called_once_with("generated_probe")
        self.assertEqual(client.last_tool_calls[0]["name"], "analyze_capability_history")
        open_url.assert_not_called()


    def test_autonomous_self_repair_request_uses_local_workflow(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "gemini_agent.client.autonomously_repair_capability",
            return_value="workflow complete",
        ) as workflow, patch("urllib.request.urlopen") as open_url:
            client = GeminiClient()
            result = client.ask(
                "Autonomously repair the generated_probe capability from failure evidence: "
                "bounded failure evidence. Do not execute anything outside the self-repair workflow."
            )
        self.assertEqual(result, "workflow complete")
        workflow.assert_called_once_with(
            capability="generated_probe",
            failure_evidence="bounded failure evidence.",
        )
        self.assertEqual(client.last_tool_calls[0]["name"], "autonomously_repair_capability")
        open_url.assert_not_called()

    def test_explicit_capability_failure_diagnosis_is_read_only_and_deterministic(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "gemini_agent.client.TOOL_HANDLERS",
            {
                **__import__("gemini_agent.tools", fromlist=["TOOL_HANDLERS"]).TOOL_HANDLERS,
                "diagnose_capability_failure": lambda capability, failure_evidence: (
                    f"diagnosed {capability}: {failure_evidence}"
                ),
            },
        ), patch(
            "urllib.request.urlopen",
        ) as open_url:
            client = GeminiClient()
            result = client.ask(
                "Diagnose a failure of the existing calculator capability. "
                "Treat this supplied evidence as genuinely FAILED: the calculator "
                "returned an incorrect result for a valid arithmetic request. "
                "Diagnose the capability using read-only evidence only."
            )
        self.assertIn("diagnosed calculator", result)
        self.assertEqual(client.last_tool_calls[0]["name"], "diagnose_capability_failure")
        open_url.assert_not_called()
    def test_explicit_repair_candidate_selection_is_read_only_and_deterministic(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "gemini_agent.client.TOOL_HANDLERS",
            {
                **__import__("gemini_agent.tools", fromlist=["TOOL_HANDLERS"]).TOOL_HANDLERS,
                "select_capability_repair_candidate": lambda capability, diagnosis: (
                    f"selected {capability}: {diagnosis}"
                ),
            },
        ), patch("urllib.request.urlopen") as open_url:
            client = GeminiClient()
            result = client.ask(
                "Select a repair candidate for the existing calculator capability after "
                "this read-only diagnosis: the calculator is locally registered, its "
                "handler is present and callable, its implementation class is LOCAL, "
                "and the recovery decision is OBSERVE_AND_ANALYZE. Treat the supplied "
                "failure evidence as genuinely FAILED: the calculator returned an "
                "incorrect result for a valid arithmetic request. Use read-only evidence "
                "only. Do not execute the calculator. Do not modify code, files, or "
                "device state."
            )
        self.assertIn("selected calculator", result)
        self.assertEqual(client.last_tool_calls[0]["name"], "select_capability_repair_candidate")
        open_url.assert_not_called()

    def test_explicit_capability_repair_is_read_only_to_model_and_deterministic(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "gemini_agent.client.TOOL_HANDLERS",
            {
                **__import__("gemini_agent.tools", fromlist=["TOOL_HANDLERS"]).TOOL_HANDLERS,
                "apply_capability_repair": lambda capability, candidate: (
                    f"repaired {capability} with {candidate}"
                ),
            },
        ), patch("urllib.request.urlopen") as open_url:
            client = GeminiClient()
            result = client.ask(
                "Apply the capability repair for the existing generated_probe capability "
                "using candidate RESTORE_GENERATED_CAPABILITY. Execute the bounded repair "
                "transaction only. Do not ask the model to choose another tool."
            )
        self.assertIn("repaired generated_probe with RESTORE_GENERATED_CAPABILITY", result)
        self.assertEqual(client.last_tool_calls[0]["name"], "apply_capability_repair")
        open_url.assert_not_called()

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