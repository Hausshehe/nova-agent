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
    def test_forced_tool_choice_retries_known_invalid_json_argument_error_once(self):
        payload = {
            "tool_choice": {
                "type": "function",
                "function": {"name": "write_text_file"},
            }
        }
        details = (
            "400 validation error: Invalid JSON: expected ident at line 1 column 2 "
            "input_value='I\\'ll complete this step.../arg_value></tool_call>'"
        )

        self.assertTrue(
            GeminiClient._should_retry_with_auto_tool_choice(400, details, payload)
        )
        self.assertFalse(
            GeminiClient._should_retry_with_auto_tool_choice(
                400, details, payload, already_retried=True
            )
        )
        self.assertFalse(
            GeminiClient._should_retry_with_auto_tool_choice(500, details, payload)
        )
        self.assertTrue(
            GeminiClient._should_retry_with_auto_tool_choice(
                400, details, {"tool_choice": "required"}
            )
        )
        self.assertFalse(
            GeminiClient._should_retry_with_auto_tool_choice(
                400, details, {"tool_choice": "required"}, already_retried=True
            )
        )
        self.assertFalse(
            GeminiClient._should_retry_with_auto_tool_choice(
                400, "Invalid JSON: expected ident at line 1 column 2", payload
            )
        )

    def test_forced_tool_choice_keeps_legacy_invalid_json_retry_detection(self):
        payload = {
            "tool_choice": {
                "type": "function",
                "function": {"name": "write_text_file"},
            }
        }
        self.assertTrue(
            GeminiClient._should_retry_with_auto_tool_choice(
                400, "Expecting value: line 1 column 1", payload
            )
        )

    def test_explicit_calculation_sequence_rejects_claims_without_matching_evidence(self):
        prompt = (
            "Calculate 19 * 23, then independently verify the result by calculating 437."
        )
        answer = "Both calculations returned 437 and verification passed."
        calls = [
            {"name": "list_saved_workflows", "args": {}, "result": '{"count": 1}'},
            {"name": "calculator", "args": {"expression": "6 * 7"}, "result": "42"},
        ]

        audited = GeminiClient._audit_explicit_calculation_sequence(prompt, answer, calls)

        self.assertIn("Execution incomplete", audited)
        self.assertIn("19*23", audited)
        self.assertIn("437", audited)
        self.assertNotIn("verification passed", audited)

    def test_explicit_calculation_sequence_executes_missing_calculator_step(self):
        prompt = (
            "Calculate 19 * 23, then independently verify the result by calculating 437."
        )
        first = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "first-calculation",
                        "type": "function",
                        "function": {
                            "name": "calculator",
                            "arguments": json.dumps({"expression": "19 * 23"}),
                        },
                    }]
                }
            }]
        }
        final = {
            "choices": [{
                "message": {"content": "Both calculations returned 437."}
            }]
        }
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(first), FakeResponse(final)],
        ):
            client = GeminiClient()
            result = client.ask(prompt)

        calculator_calls = [
            call for call in client.last_tool_calls if call["name"] == "calculator"
        ]
        self.assertEqual(
            [call["args"]["expression"] for call in calculator_calls],
            ["19 * 23", "437"],
        )
        self.assertEqual(
            [call["result"] for call in calculator_calls],
            ["437", "437"],
        )
        self.assertEqual(result, "Both calculations returned 437.")

    def test_explicit_calculation_sequence_accepts_matching_tool_evidence(self):
        prompt = (
            "Calculate 19 * 23, then independently verify the result by calculating 437."
        )
        calls = [
            {"name": "calculator", "args": {"expression": "19 * 23"}, "result": "437"},
            {"name": "calculator", "args": {"expression": "437"}, "result": "437"},
        ]

        audited = GeminiClient._audit_explicit_calculation_sequence(
            prompt, "Both calculations are verified.", calls
        )

        self.assertEqual(audited, "Both calculations are verified.")

    def test_explicit_workflow_request_excludes_atomic_tools_from_provider_schema(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ):
            client = GeminiClient()
            contents = [{
                "role": "user",
                "parts": [{
                    "text": (
                        'Use run_workflow, not calculator directly, to calculate with a structured steps array '
                        'containing calculator arguments for 6 * 7.'
                    )
                }],
            }]
            requested_tool = client._requested_local_tool(contents)
            declarations = client._relevant_tool_declarations(contents)

        self.assertEqual(requested_tool, "run_workflow")
        self.assertEqual([item["name"] for item in declarations], ["run_workflow"])
        schema = declarations[0]["parameters"]["properties"]["steps"]
        self.assertEqual(schema["type"], "ARRAY")

    def test_natural_language_run_workflow_request_excludes_atomic_tools(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ):
            client = GeminiClient()
            contents = [{
                "role": "user",
                "parts": [{
                    "text": (
                        'Run a workflow with two steps: step 0 calls calculator with '
                        'expression "6 * 7"; step 1 calls calculator with expression '
                        '{"$step_result": 0}. Report each actual step result. Do not save it.'
                    )
                }],
            }]
            requested_tool = client._requested_local_tool(contents)
            declarations = client._relevant_tool_declarations(contents)

        self.assertEqual(requested_tool, "run_workflow")
        self.assertEqual([item["name"] for item in declarations], ["run_workflow"])

    def test_saved_workflow_discovery_evidence_overrides_model_denial(self):
        response = {
            "choices": [{
                "message": {
                    "content": (
                        "I do not have access to a tool to list saved workflows and inspect "
                        "their descriptions. Therefore, I cannot determine if any existing "
                        "workflow fits."
                    )
                }
            }]
        }
        discovery = json.dumps({
            "count": 1,
            "workflows": [{
                "name": "persistence-check",
                "description": "Verify reusable workflow persistence",
                "steps": 2,
            }],
        })
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(response),
        ):
            client = GeminiClient()
            client.tool_handlers["list_saved_workflows"] = unittest.mock.Mock(
                return_value=discovery
            )
            result = client.ask(
                "List the saved workflows and inspect their descriptions."
            )

        client.tool_handlers["list_saved_workflows"].assert_called_once_with()
        self.assertIn("persistence-check", result)
        self.assertIn("Verify reusable workflow persistence", result)
        self.assertNotIn("do not have access", result.lower())

    def test_explicit_saved_workflow_discovery_runs_before_provider_decision(self):
        response = {
            "choices": [{
                "message": {
                    "content": "No saved workflow fits; direct calculation is appropriate."
                }
            }]
        }
        discovery = '{"workflows":[{"name":"example","description":"Unrelated file cleanup"}]}'
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(response),
        ) as urlopen_mock:
            client = GeminiClient()
            client.tool_handlers["list_saved_workflows"] = unittest.mock.Mock(
                return_value=discovery
            )
            result = client.ask(
                "List the saved workflows and inspect their descriptions. If none fits, calculate 19 * 23."
            )

        client.tool_handlers["list_saved_workflows"].assert_called_once_with()
        request_payload = json.loads(urlopen_mock.call_args.args[0].data.decode())
        offered_tools = {
            item["function"]["name"] for item in request_payload["tools"]
        }
        self.assertNotIn("list_saved_workflows", offered_tools)
        self.assertIn("calculator", offered_tools)
        self.assertEqual(client.last_tool_calls[0], {
            "name": "list_saved_workflows",
            "args": {},
            "result": discovery,
        })
        self.assertIn("No saved workflow fits", result)

    def test_explicit_named_saved_workflow_inspection_runs_before_provider_decision(self):
        response = {
            "choices": [{
                "message": {
                    "content": "Inspection result received; direct calculation is appropriate."
                }
            }]
        }
        inspection = '{"name":"persistence-check","description":"Verify reusable workflow persistence","steps":[{"index":0,"tool":"calculator","arguments":{"expression":"6 * 7"}},{"index":1,"tool":"calculator","arguments":{"expression":{"$step_result":0}}}],"note":"Definition inspected only. No workflow was executed."}'
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(response),
        ) as urlopen_mock:
            client = GeminiClient()
            client.tool_handlers["list_saved_workflows"] = unittest.mock.Mock(
                return_value='{"count":1,"workflows":[{"name":"persistence-check","description":"Verify reusable workflow persistence","steps":2}]}'
            )
            client.tool_handlers["inspect_saved_workflow"] = unittest.mock.Mock(
                return_value=inspection
            )
            result = client.ask(
                "List the saved workflows. Inspect persistence-check by its exact name and report its actual steps without executing it."
            )

        client.tool_handlers["list_saved_workflows"].assert_called_once_with()
        client.tool_handlers["inspect_saved_workflow"].assert_called_once_with(
            name="persistence-check"
        )
        self.assertEqual(
            [call["name"] for call in client.last_tool_calls],
            ["list_saved_workflows", "inspect_saved_workflow"],
        )
        self.assertEqual(client.last_tool_calls[1]["result"], inspection)
        request_payload = json.loads(urlopen_mock.call_args.args[0].data.decode())
        offered_tools = {
            item["function"]["name"] for item in request_payload["tools"]
        }
        self.assertNotIn("inspect_saved_workflow", offered_tools)
        self.assertTrue(any("Saved-workflow inspection result:" in message["content"] for message in request_payload["messages"]))
        self.assertIn("Inspection result received", result)

    def test_goal_relevant_tools_keep_saved_workflow_discovery_and_execution_available(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ):
            client = GeminiClient()
            contents = [{
                "role": "user",
                "parts": [{"text": "Inspect saved workflows and their descriptions; use one only if it fits, otherwise calculate 6 * 7."}],
            }]
            declarations = client._relevant_tool_declarations(contents)

        names = {item["name"] for item in declarations}
        self.assertIn("calculator", names)
        self.assertIn("list_saved_workflows", names)
        self.assertIn("inspect_saved_workflow", names)
        self.assertIn("run_saved_workflow", names)

    def test_unrelated_narrow_intent_excludes_saved_workflow_tools(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ):
            client = GeminiClient()
            contents = [{
                "role": "user",
                "parts": [{"text": "What is the current battery level?"}],
            }]
            declarations = client._relevant_tool_declarations(contents)

        self.assertEqual(
            [item["name"] for item in declarations],
            ["get_system_battery_status"],
        )

    def test_mixed_workflow_and_calculator_goal_exposes_saved_workflow_tools(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ):
            client = GeminiClient()
            contents = [{
                "role": "user",
                "parts": [{
                    "text": "Inspect saved workflows and their descriptions; calculate 19 * 23 if none fits."
                }],
            }]
            declarations = client._relevant_tool_declarations(contents)

        names = {item["name"] for item in declarations}
        self.assertIn("calculator", names)
        self.assertIn("list_saved_workflows", names)
        self.assertIn("run_saved_workflow", names)

    def test_client_dispatches_registered_workflow_and_returns_step_evidence(self):
        workflow_steps = json.dumps([
            {"tool": "calculator", "arguments": {"expression": "6 * 7"}},
            {"tool": "calculator", "arguments": {"expression": {"$step_result": 0}}},
        ])
        tool_call = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "workflow-test",
                        "type": "function",
                        "function": {
                            "name": "run_workflow",
                            "arguments": json.dumps({"steps": workflow_steps}),
                        },
                    }]
                }
            }]
        }
        final = {"choices": [{"message": {"content": "Both workflow steps completed."}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(tool_call), FakeResponse(final)],
        ) as open_url:
            client = GeminiClient()
            result = client.ask("Run a two-step read-only workflow and report its results.")

        self.assertEqual(result, "Both workflow steps completed.")
        self.assertEqual([trace["name"] for trace in client.last_tool_calls], ["run_workflow"])
        workflow_result = json.loads(client.last_tool_calls[0]["result"])
        self.assertEqual(workflow_result["status"], "completed")
        self.assertEqual(workflow_result["steps"][1]["result"], "42")
        first_payload = json.loads(open_url.call_args_list[0].args[0].data)
        declaration = next(
            item["function"] for item in first_payload["tools"]
            if item["function"]["name"] == "run_workflow"
        )
        self.assertIn("steps", declaration["parameters"]["properties"])


    def test_malformed_text_tool_arguments_retry_with_registered_schema(self):
        malformed = {
            "choices": [{
                "message": {
                    "content": (
                        "<tool_call>find_executable"
                        "<arg_key>pattern</arg_key><arg_value>aapt</arg_value>"
                        "</tool_call>"
                    )
                }
            }]
        }
        valid_call = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "find-aapt",
                        "type": "function",
                        "function": {
                            "name": "find_executable",
                            "arguments": json.dumps({"name": "aapt"}),
                        },
                    }]
                }
            }]
        }
        final = {"choices": [{"message": {"content": "Executable inspected."}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[
                FakeResponse(malformed),
                FakeResponse(valid_call),
                FakeResponse(final),
            ],
        ) as open_url:
            client = GeminiClient()
            client.tool_handlers["find_executable"] = lambda name: f"FOUND:{name}"
            result = client.ask("Inspect the available executable named aapt.")

        self.assertEqual(result, "Executable inspected.")
        self.assertEqual(
            [trace["name"] for trace in client.last_tool_calls],
            ["find_executable"],
        )
        self.assertEqual(client.last_tool_calls[0]["args"], {"name": "aapt"})
        self.assertIn("FOUND:aapt", str(client.last_tool_calls[0]["result"]))
        retry_payload = json.loads(open_url.call_args_list[1].args[0].data)
        retry_tool = retry_payload["tools"][0]["function"]
        self.assertEqual(retry_tool["name"], "find_executable")
        self.assertIn("name", retry_tool["parameters"]["properties"])
        self.assertNotIn("pattern", retry_tool["parameters"]["properties"])

    def test_repeated_malformed_text_tool_call_never_leaks_as_success(self):
        malformed = {
            "choices": [{
                "message": {
                    "content": (
                        "<tool_call>find_executable"
                        "<arg_key>pattern</arg_key><arg_value>aapt</arg_value>"
                        "</tool_call>"
                    )
                }
            }]
        }
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(malformed), FakeResponse(malformed)],
        ):
            client = GeminiClient()
            client.tool_handlers["find_executable"] = lambda name: f"FOUND:{name}"
            result = client.ask("Inspect the available executable named aapt.")

        self.assertIn("No action executed", result)
        self.assertIn("schema-correction retry", result)
        self.assertNotIn("<tool_call>", result)
        self.assertEqual(client.last_tool_calls, [])

    def test_unregistered_text_tool_name_retries_with_available_tools(self):
        invented = {
            "choices": [{
                "message": {
                    "content": (
                        "<tool_call>calculate_workflow"
                        "<arg_key>workflow</arg_key><arg_value>show_workflows</arg_value>"
                        "</tool_call>"
                    )
                }
            }]
        }
        discovery = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "discover-saved-workflows",
                        "type": "function",
                        "function": {
                            "name": "list_saved_workflows",
                            "arguments": "{}",
                        },
                    }]
                }
            }]
        }
        final = {"choices": [{"message": {"content": "No saved workflow fits."}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[
                FakeResponse(invented),
                FakeResponse(discovery),
                FakeResponse(final),
            ],
        ) as open_url:
            client = GeminiClient()
            result = client.ask(
                "Inspect saved workflows and use only registered tools to complete the request."
            )

        self.assertEqual(result, "No saved workflow fits.")
        self.assertEqual(
            [trace["name"] for trace in client.last_tool_calls],
            ["list_saved_workflows"],
        )
        retry_payload = json.loads(open_url.call_args_list[1].args[0].data)
        self.assertEqual(retry_payload["tool_choice"], "auto")
        self.assertTrue(retry_payload["tools"])
        retry_messages = retry_payload["messages"]
        self.assertIn("not registered and was not executed", retry_messages[-1]["content"])

    def test_requires_cloudflare_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "CLOUDFLARE_API_TOKEN"):
                GeminiClient()

    def test_repeated_observation_excludes_stalled_tools_but_keeps_alternatives(self):
        payload = {
            "tools": [
                {"type": "function", "function": {"name": "read_text_file"}},
                {"type": "function", "function": {"name": "write_text_file"}},
                {"type": "function", "function": {"name": "run_command"}},
            ],
            "tool_choice": {"type": "function", "function": {"name": "read_text_file"}},
        }
        changed = GeminiClient._exclude_repeated_observation_tools(
            payload,
            [
                {"name": "read_text_file", "args": {"path": "workspace/a.txt"}, "result": "same"},
                {"name": "read_text_file", "args": {"path": "workspace/a.txt"}, "result": "same"},
            ],
        )
        self.assertTrue(changed)
        names = [tool["function"]["name"] for tool in payload["tools"]]
        self.assertEqual(names, ["write_text_file", "run_command"])
        self.assertEqual(payload["tool_choice"], "auto")

    def test_repeated_observation_stops_if_no_distinct_tool_remains(self):
        payload = {
            "tools": [
                {"type": "function", "function": {"name": "read_text_file"}},
            ],
            "tool_choice": "auto",
        }
        changed = GeminiClient._exclude_repeated_observation_tools(
            payload, [{"name": "read_text_file", "args": {}, "result": "same"}]
        )
        self.assertFalse(changed)
        self.assertEqual(
            [tool["function"]["name"] for tool in payload["tools"]],
            ["read_text_file"],
        )

    def test_tool_loop_exhaustion_reports_bounded_names_without_tool_output(self):
        trace = [
            {"name": "select_goal_next_step", "args": {}, "result": "Next step: write_text_file\\nReason: create source"},
            {"name": "write_text_file", "args": {"path": "workspace/src/Main.java", "content": "private file content"}, "result": "File written"},
            {"name": "discover_dependency_options", "result": "private or lengthy result"},
            {"name": "acquire_termux_packages", "result": "another lengthy result"},
            {"name": "discover_dependency_options", "result": "sensitive result"},
        ]
        diagnostic = GeminiClient._tool_loop_exhaustion_diagnostic(
            16, trace, goal_state=type("Goal", (), {"status": "ACTIVE"})()
        )
        self.assertIn("16 rounds", diagnostic)
        self.assertIn(
            "discover_dependency_options -> acquire_termux_packages -> discover_dependency_options",
            diagnostic,
        )
        self.assertIn("discover_dependency_options x2", diagnostic)
        self.assertIn("Goal state: ACTIVE", diagnostic)
        self.assertIn("selector chose write_text_file", diagnostic)
        self.assertIn("write_text_file path=workspace/src/Main.java", diagnostic)
        self.assertNotIn("private file content", diagnostic)
        self.assertNotIn("private or lengthy result", diagnostic)
        self.assertNotIn("sensitive result", diagnostic)

    def test_identical_failed_file_write_is_suppressed(self):
        previous = [{
            "name": "write_text_file",
            "args": {"path": "calc-app/settings.gradle", "content": "plugins {}"},
            "result": "Tool error: Permission denied",
        }]
        self.assertTrue(GeminiClient._same_failed_write(
            {"path": "calc-app/settings.gradle", "content": "plugins {}"}, previous
        ))
        self.assertFalse(GeminiClient._same_failed_write(
            {"path": "calc-app/settings.gradle", "content": "plugins { id 'application' }"}, previous
        ))
        self.assertFalse(GeminiClient._same_failed_write(
            {"path": "calc-app/app/build.gradle", "content": "plugins {}"}, previous
        ))

    def test_tool_loop_exhaustion_reports_write_error_without_file_contents(self):
        trace = [
            {
                "name": "write_text_file",
                "args": {"path": "calc-app/settings.gradle", "content": "private source"},
                "result": "Tool error: Permission denied while creating parent directory",
            }
        ]
        diagnostic = GeminiClient._tool_loop_exhaustion_diagnostic(
            16, trace, goal_state=type("Goal", (), {"status": "ACTIVE"})()
        )
        self.assertIn("write_text_file path=calc-app/settings.gradle outcome=error", diagnostic)
        self.assertIn("Permission denied while creating parent directory", diagnostic)
        self.assertNotIn("private source", diagnostic)

    def test_groq_provider_requires_its_own_api_key(self):
        with patch.dict(os.environ, {"NOVA_PROVIDER": "groq"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "GROQ_API_KEY"):
                GeminiClient()

    def test_groq_provider_routes_request_to_groq(self):
        response = {"choices": [{"message": {"content": "Groq works"}}]}
        captured = []

        def fake_urlopen(request, timeout=180):
            captured.append(request)
            return FakeResponse(response)

        with patch.dict(os.environ, {
            "NOVA_PROVIDER": "groq",
            "GROQ_API_KEY": "test-groq-key",
        }, clear=True), patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client = GeminiClient()
            result = client.ask("Reply with a short greeting.")

        self.assertEqual(result, "Groq works")
        self.assertEqual(captured[0].full_url, "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(captured[0].get_header("Authorization"), "Bearer test-groq-key")
        self.assertEqual(json.loads(captured[0].data)["model"], "openai/gpt-oss-20b")

    def test_openrouter_provider_requires_its_own_api_key(self):
        with patch.dict(os.environ, {"NOVA_PROVIDER": "openrouter"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "OPENROUTER_API_KEY"):
                GeminiClient()

    def test_openrouter_free_route_uses_openrouter_endpoint_and_key(self):
        response = {"choices": [{"message": {"content": "fallback works"}}]}
        captured = []

        def fake_urlopen(request, timeout=180):
            captured.append(request)
            return FakeResponse(response)

        with patch.dict(os.environ, {
            "NOVA_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "test-openrouter-key",
        }, clear=True), patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client = GeminiClient()
            result = client.ask("Reply with a short greeting.")

        self.assertEqual(result, "fallback works")
        self.assertEqual(captured[0].full_url, "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(captured[0].get_header("Authorization"), "Bearer test-openrouter-key")
        self.assertEqual(json.loads(captured[0].data)["model"], "openrouter/free")

    def test_gemini_provider_requires_its_own_api_key(self):
        with patch.dict(os.environ, {"NOVA_PROVIDER": "gemini"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
                GeminiClient()

    def test_gemini_provider_routes_request_to_gemini_openai_compatible_endpoint(self):
        response = {"choices": [{"message": {"content": "Gemini works"}}]}
        captured = []

        def fake_urlopen(request, timeout=180):
            captured.append(request)
            return FakeResponse(response)

        with patch.dict(os.environ, {
            "NOVA_PROVIDER": "gemini",
            "GEMINI_API_KEY": "test-gemini-key",
        }, clear=True), patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client = GeminiClient()
            result = client.ask("Reply with a short greeting.")

        self.assertEqual(result, "Gemini works")
        self.assertEqual(
            captured[0].full_url,
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        )
        self.assertEqual(captured[0].get_header("Authorization"), "Bearer test-gemini-key")
        self.assertEqual(json.loads(captured[0].data)["model"], "gemini-3.5-flash-lite")

    def test_recovers_missing_request_argument_from_active_prompt(self):
        first_response = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "recover-request",
                        "type": "function",
                        "function": {
                            "name": "discover_android_mechanisms",
                            "arguments": "{}",
                        },
                    }]
                }
            }]
        }
        second_response = {"choices": [{"message": {"content": "continued"}}]}
        captured = []

        def discover(request):
            captured.append(request)
            return "discovery evidence"

        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", side_effect=[
            FakeResponse(first_response),
            FakeResponse(second_response),
        ]):
            client = GeminiClient(tool_handlers={
                "discover_android_mechanisms": discover,
            })
            result = client.ask("Build an unfamiliar artifact using available mechanisms.")

        self.assertEqual(result, "continued")
        self.assertEqual(
            captured,
            ["Build an unfamiliar artifact using available mechanisms."],
        )

    def test_calculator_app_construction_does_not_route_to_arithmetic_tool(self):
        prompt = (
            "Create a minimal Android calculator app from scratch in a new workspace. "
            "Inspect the available environment and discover the necessary tools and build procedure. "
            "Create the source files and configuration, build an installable APK, and verify addition, "
            "subtraction, multiplication, and division with actual tests. Maintain ownership of this "
            "goal through failures: diagnose the evidence, recover or replan, and continue until the "
            "success criteria are verified or a genuine environmental blocker is demonstrated. "
            "Do not claim success without evidence. Report the workspace, source files, build command, "
            "APK path, test results, and any unresolved blockers."
        )
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ):
            client = GeminiClient()

        self.assertIsNone(
            client._requested_local_tool(contents),
            "The word 'calculator' names the artifact, not a request for arithmetic.",
        )
        names = {
            item["name"] for item in client._relevant_tool_declarations(contents)
        }
        self.assertNotIn(
            "calculator", names,
            "Construction acceptance criteria mentioning arithmetic must not expose the arithmetic tool.",
        )
        self.assertIn("execute_constructed_action", names)
        self.assertIn("write_text_file", names)

    def test_generic_autonomous_build_benchmark_enters_goal_orchestration(self):
        prompt = (
            "Create a minimal Android calculator app from scratch in a new workspace. "
            "Inspect the available environment and discover the necessary tools and build procedure. "
            "Create the source files and configuration, build an installable APK, and verify addition, "
            "subtraction, multiplication, and division with actual tests. Maintain ownership of this "
            "goal through failures: diagnose the evidence, recover or replan, and continue until the "
            "success criteria are verified or a genuine environmental blocker is demonstrated. "
            "Do not claim success without evidence. Report the workspace, source files, build command, "
            "APK path, test results, and any unresolved blockers."
        )
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch.object(
            GeminiClient, "_generate_cloudflare", return_value="orchestration-routed"
        ) as generate:
            client = GeminiClient()
            answer = client.ask(prompt)
        self.assertEqual(answer, "orchestration-routed")
        routed_prompt = generate.call_args.args[0][-1]["parts"][0]["text"]
        self.assertIn("[Nova orchestration directive]", routed_prompt)
        self.assertIsNotNone(client.goal_state)
        self.assertEqual(client.goal_state.status, "ACTIVE")
        self.assertEqual(
            client.goal_state.goal,
            "Create a minimal Android calculator app from scratch in a new workspace.",
            "The persisted goal must describe the construction task, not the reporting request.",
        )
        success_condition = client.goal_state.success_condition
        self.assertEqual(
            success_condition,
            "Create the source files and configuration, build an installable APK, and verify addition, "
            "subtraction, multiplication, and division with actual tests.",
            "The success condition must preserve the concrete build and test contract.",
        )
        routed_prompt = generate.call_args.args[0][-1]["parts"][0]["text"]
        self.assertIn(f'Goal: "{client.goal_state.goal}".', routed_prompt)
        self.assertIn(f'Success condition: "{success_condition}".', routed_prompt)

    def test_dependency_recovery_prompt_starts_persistent_goal_and_exposes_construction_tools(self):
        prompt = (
            "Continue from the real current environment. Inspect installed dependencies first. "
            "You may install necessary packages from configured Termux repositories using your "
            "registered dependency-acquisition tools. Choose the smallest viable build strategy, "
            "verify every installation, and continue through building and arithmetic testing. "
            "Do not ask me to install dependencies manually. If a required component is unavailable, "
            "investigate a different legitimate route before declaring a blocker."
        )
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch.object(
            GeminiClient, "_generate_cloudflare", return_value="orchestration-routed"
        ) as generate:
            client = GeminiClient()
            answer = client.ask(prompt)
        self.assertEqual(answer, "orchestration-routed")
        self.assertIsNotNone(client.goal_state)
        self.assertEqual(client.goal_state.status, "ACTIVE")
        self.assertIn("install dependencies manually", client.goal_state.goal.lower())
        self.assertTrue(client.goal_state.success_condition)
        routed_prompt = generate.call_args.args[0][-1]["parts"][0]["text"]
        self.assertIn("[Nova orchestration directive]", routed_prompt)
        available_names = {
            declaration["name"]
            for declaration in client._relevant_tool_declarations(generate.call_args.args[0])
        }
        self.assertIn("discover_dependency_options", available_names)
        self.assertIn("acquire_termux_packages", available_names)
        self.assertIn("write_text_file", available_names)
        self.assertIn("run_command", available_names)
        self.assertIn("verify_command_result", available_names)

    def test_descriptive_build_request_does_not_start_autonomous_mutation(self):
        prompt = "Create an Android calculator app and explain how to build and verify it."
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch.object(
            GeminiClient, "_generate_cloudflare", return_value="descriptive-answer"
        ) as generate:
            client = GeminiClient()
            answer = client.ask(prompt)
        self.assertEqual(answer, "descriptive-answer")
        self.assertIsNone(client.goal_state)
        routed_prompt = generate.call_args.args[0][-1]["parts"][0]["text"]
        self.assertNotIn("[Nova orchestration directive]", routed_prompt)

    def test_explicit_construction_request_enters_goal_orchestration(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch.object(GeminiClient, "_generate_cloudflare", return_value="orchestration-routed") as generate:
            client = GeminiClient()
            answer = client.ask(
                "Create a minimal Android app from scratch. "
                "You must determine the required files and execute the required actions. "
                "Do not ask me to write or modify code manually. "
                "Build the APK and verify the resulting artifact with evidence."
            )
        self.assertEqual(answer, "orchestration-routed")
        routed_prompt = generate.call_args.args[0][-1]["parts"][0]["text"]
        self.assertIn("[Nova orchestration directive]", routed_prompt)
        self.assertIn('Nova has already established the runtime goal contract', routed_prompt)
        self.assertIn('Goal: "Create a minimal Android app from scratch."', routed_prompt)
        self.assertIn('Success condition: "Build the APK and verify the resulting artifact with evidence."', routed_prompt)
        self.assertIn("Autonomously pursue the goal", routed_prompt)
        self.assertIsNotNone(client.goal_state)
        self.assertEqual(client.goal_state.status, "ACTIVE")
        self.assertEqual(client.goal_state.goal, "Create a minimal Android app from scratch.")
        self.assertEqual(
            client.goal_state.success_condition,
            "Build the APK and verify the resulting artifact with evidence.",
        )

    def test_goal_contract_initializes_runtime_goal_state_without_execution(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen") as open_url:
            client = GeminiClient()
            answer = client.ask(
                'Establish a goal contract for "check the device battery" with success condition '
                '"the current battery status is successfully reported". Do not execute any action '
                'or modify device state.'
            )
        self.assertIn("Runtime goal state: ACTIVE", answer)
        self.assertIn("Runtime evidence: 0 entries", answer)
        self.assertEqual(
            client.goal_state.snapshot(),
            {
                "goal": "check the device battery",
                "success_condition": "the current battery status is successfully reported",
                "status": "ACTIVE",
                "progress_status": "INCONCLUSIVE",
                "progress_reason": "No goal-progress observation has been recorded.",
                "evidence": [],
                "steps": [],
                "recovery_history": [],
            },
        )
        self.assertIn("Action executed: No", answer)
        open_url.assert_not_called()

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

    def test_unknown_provider_tool_is_reported_and_does_not_abort_request(self):
        responses = [
            {
                "choices": [{
                    "message": {
                        "tool_calls": [{
                            "id": "unknown-workspace-call",
                            "type": "function",
                            "function": {
                                "name": "request_workspace",
                                "arguments": "{}",
                            },
                        }]
                    }
                }]
            },
            {"choices": [{"message": {"content": "Recovered after unknown tool."}}]},
        ]
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(item) for item in responses],
        ) as open_url:
            client = GeminiClient()
            answer = client.ask("Please give a short project status summary.")

        self.assertEqual(answer, "Recovered after unknown tool.")
        self.assertEqual(open_url.call_count, 2)
        self.assertEqual(client.last_tool_calls[0]["name"], "request_workspace")
        self.assertIn("unregistered tool", client.last_tool_calls[0]["result"].lower())
        self.assertIn("no action was executed", client.last_tool_calls[0]["result"].lower())


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

    def test_unregistered_strategy_is_blocked_before_provider_execution(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen") as open_url:
            client = GeminiClient()
            with patch(
                "gemini_agent.learning.select_verified_strategy",
                return_value=(
                    "Verified strategy selection: retry_safe\\n"
                    "Candidates: ['retry_safe', 'fallback_probe']\\n"
                    "Selection basis: verified experience ranking changed the preferred candidate\\n"
                    "Safety boundary: selection is a preference only; validation and execution verification remain authoritative.\\n"
                    "No strategy execution or device state change was performed."
                ),
            ):
                result = client.ask(
                    'Use the normal decision process for request "recover a failed network check". '
                    'I have two candidate strategies: "retry_safe" and "fallback_probe".'
                )
        self.assertIn("Verified strategy selection blocked before execution.", result)
        self.assertIn("Selected strategy: retry_safe", result)
        self.assertIn("no registered executable tool", result)
        self.assertIn("STOPPED SAFELY", result)
        open_url.assert_not_called()

    def test_failed_command_enters_automatic_diagnosis_and_recovery(self):
        followup = {"choices": [{"message": {"content": "recovery complete"}}]}
        response = {
            "choices": [{"message": {"tool_calls": [{
                "id": "failed-command",
                "type": "function",
                "function": {
                    "name": "run_command",
                    "arguments": json.dumps({"command": "python -c \"import sys; sys.exit(1)\""}),
                },
            }]}}]
        }
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(response), FakeResponse(followup)],
        ):
            client = GeminiClient(tool_handlers={
                "run_command": lambda command: "Exit code: 1\\nstderr: failed",
                "diagnose_command_failure": lambda command, error: "Diagnosis: transient command failure.",
                "recover_command": lambda command, expected: "Outcome: FAILED\\nAttempts: 2",
            })
            answer = client.ask(
                'Use run_command to execute the safe command "python -c "import sys; sys.exit(1)"". '
                'If that execution returns a nonzero exit code, automatically diagnose the failed run_command '
                'outcome and then hand it to the existing bounded recover_command path. '
                'Do not call recover_command as the initial execution strategy. '
                'Do not modify device state. Expected postcondition is "Python".'
            )
        self.assertEqual(
            client.last_tool_calls[0]["args"]["command"],
            "python -c " + '"import sys; sys.exit(1)"',
        )
        recovery_report = client.last_tool_calls[-1]["result"]
        self.assertIn("Automatic tool recovery:", recovery_report)
        self.assertIn("Failed tool: run_command", recovery_report)
        self.assertIn("Original tool result:", recovery_report)
        self.assertIn("Exit code: 1", recovery_report)
        self.assertIn("Diagnosis: transient command failure.", recovery_report)
        self.assertIn("Outcome: FAILED", recovery_report)
        self.assertIn("Attempts: 2", recovery_report)
        self.assertEqual(recovery_report.count("Diagnosis: transient command failure."), 1)

    def test_verified_recovery_outcome_is_automatically_learned(self):
        client = object.__new__(GeminiClient)
        client.tool_handlers = {
            "diagnose_command_failure": lambda command, error: "Diagnosis: bounded failure.",
            "recover_command": lambda command, expected: "Outcome: VERIFIED\nRecovery succeeded.\nPostcondition: VERIFIED: expected text found: activity",
        }
        with patch(
            "gemini_agent.learning.record_verified_experience",
            return_value="Verified experience learned.",
        ) as record:
            result = client._coordinate_tool_failure(
                local_name="run_command",
                args={"command": "python --version"},
                tool_result="Exit code: 1\nstderr: transient",
                request_text="Recover the failed network check.",
            )
        self.assertIn("Recovery learning:", result)
        self.assertIn("Verified experience learned.", result)
        record.assert_called_once_with(
            "Recover the failed network check.",
            "recover_command",
            "Outcome: VERIFIED\nRecovery succeeded.\nPostcondition: VERIFIED: expected text found: activity",
            domain="general",
        )

    def test_failed_strategy_outcome_is_automatically_learned_for_future_avoidance(self):
        client = object.__new__(GeminiClient)
        client.tool_handlers = {
            "diagnose_command_failure": lambda command, error: "Diagnosis: bounded failure.",
            "recover_command": lambda command, expected: "Outcome: VERIFIED\nRecovery succeeded.",
        }
        with patch("gemini_agent.learning.record_verified_failure", return_value="Verified failed experience learned.") as record:
            result = client._coordinate_tool_failure(
                local_name="run_command",
                args={"command": "dumpsys -l"},
                tool_result="Tool error: Command is not allowed: dumpsys\nOutcome: FAILED",
                request_text="Recover a failed Android diagnostic check.",
            )
        self.assertIn("Failure learning:", result)
        self.assertIn("Verified failed experience learned.", result)
        record.assert_called_once_with(
            "Recover a failed Android diagnostic check.",
            "run_command",
            "Tool error: Command is not allowed: dumpsys\nOutcome: FAILED",
            domain="general",
        )

    def test_generic_failed_tool_stops_safely_without_unbounded_recovery(self):
        client = object.__new__(GeminiClient)
        client.tool_handlers = {}
        result = client._coordinate_tool_failure(
            local_name="test_tool",
            args={},
            tool_result="Outcome: FAILED\\nreason: bounded test failure",
            request_text="Handle the failed tool safely.",
        )
        self.assertIn("Automatic tool recovery:", result)
        self.assertIn("Failed tool: test_tool", result)
        self.assertIn("no bounded recovery path is registered for this tool", result)
        self.assertIn("Outcome: FAILED", result)
        self.assertIn("Action: stop safely.", result)

    def test_compound_directory_creation_and_existence_request_stays_in_tool_loop(self):
        request = (
            'Using only existing registered filesystem tools, explicitly create a new directory '
            'named "foundation-directory-test". Call make_directory first, then call path_exists '
            'on that exact directory. Report each result and do not use shell commands.'
        )
        selected = GeminiClient._requested_local_tool([
            {"role": "user", "parts": [{"text": request}]}
        ])
        self.assertIsNone(selected)

    def test_standalone_path_exists_request_still_routes_directly(self):
        request = "Use the path_exists tool to check whether foundation-directory-test exists."
        selected = GeminiClient._requested_local_tool([
            {"role": "user", "parts": [{"text": request}]}
        ])
        self.assertEqual(selected, "path_exists")

    def test_compound_run_command_request_routes_execution_before_recovery_mentions(self):
        request = (
            'Use run_command to execute the safe command "python -c \\"import sys; sys.exit(1)\\"". '
            'If that execution returns a nonzero exit code, automatically diagnose the failed '
            'run_command outcome and then hand it to the existing bounded recover_command path. '
            'Do not call recover_command as the initial execution strategy. Do not modify device state.'
        )
        selected = GeminiClient._requested_local_tool([
            {"role": "user", "parts": [{"text": request}]}
        ])
        self.assertEqual(selected, "run_command")

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
                'Choose between strategy "calculator" and strategy "run_command" '
                'for calculating a value.'
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

    def test_selected_run_command_preserves_explicit_command(self):
        responses = [
            {
                "choices": [{
                    "message": {
                        "tool_calls": [{
                            "id": "run-command-call",
                            "type": "function",
                            "function": {
                                "name": "run_command",
                                "arguments": json.dumps({"command": "run_command -l"}),
                            },
                        }]
                    }
                }]
            },
            {"choices": [{"message": {"content": "done"}}]},
        ]
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(item) for item in responses],
        ), patch(
            "gemini_agent.learning.select_verified_strategy",
            return_value="Verified strategy selection: run_command",
        ):
            client = GeminiClient()
            calls = []
            client.tool_handlers["run_command"] = lambda command: calls.append(command) or "Exit code: 0\nstdout: diagnostic"
            answer = client.ask(
                'Use the normal decision process for request "recover a failed Android diagnostic check". '
                'I have two candidate strategies: "run_command" and "calculator". '
                'Execute the selected strategy exactly once with command "dumpsys -l" and expected text "activity".'
            )
        self.assertEqual(answer, "done")
        self.assertEqual(calls, ["dumpsys -l"])

    def test_normal_decision_loop_learns_verified_outcome_for_selected_strategy(self):
        responses = [
            {
                "choices": [{
                    "message": {
                        "tool_calls": [{
                            "id": "calculator-call",
                            "type": "function",
                            "function": {
                                "name": "calculator",
                                "arguments": json.dumps({"expression": "17 * 23"}),
                            },
                        }]
                    }
                }]
            },
            {"choices": [{"message": {"content": "done"}}]},
        ]
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(item) for item in responses],
        ), patch(
            "gemini_agent.learning.select_verified_strategy",
            return_value="Verified strategy selection: calculator",
        ), patch(
            "gemini_agent.learning.record_verified_experience",
            return_value="Verified experience learned.",
        ) as recorder:
            def verified_calculator(expression):
                return "Verification: VERIFIED: calculator result confirmed."
            client = GeminiClient(tool_handlers={"calculator": verified_calculator})
            answer = client.ask(
                'I need to perform a calculation. I have two candidate strategies: "fallback_probe" and "calculator". '
                'Use the normal decision process to choose which strategy should be preferred first based on verified experience.'
            )
        self.assertEqual(answer, "done")
        recorder.assert_called_once_with(
            "perform a calculation",
            "calculator",
            "Verification: VERIFIED: calculator result confirmed.",
            domain="general",
        )
        self.assertEqual(client.last_tool_calls[-1]["verified_experience_learning"], "Verified experience learned.")

    def test_selected_strategy_receives_required_result_before_execution(self):
        responses = [
            {
                "choices": [{
                    "message": {
                        "tool_calls": [{
                            "id": "verify-call",
                            "type": "function",
                            "function": {
                                "name": "verify_command_result",
                                "arguments": json.dumps({"result": "", "expected": "ok"}),
                            },
                        }]
                    }
                }]
            },
            {"choices": [{"message": {"content": "done"}}]},
        ]
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(item) for item in responses],
        ), patch(
            "gemini_agent.learning.select_verified_strategy",
            return_value="Verified strategy selection: verify_command_result",
        ):
            client = GeminiClient(
                tool_handlers={
                    "verify_command_result": lambda result, expected: (
                        f"Verification: VERIFIED: expected text found: {expected}"
                        if expected in result
                        else f"Verification: FAILED: expected text not found: {expected}"
                    ),
                    "run_command": lambda command: "Exit code: 0\nstdout:\nok",
                }
            )
            client.ask(
                'Use the normal decision process with command "printf ok" and expected text "ok". '
                'I have candidate strategies "fallback_probe" and "verify_command_result".'
            )
        verify_calls = [
            call for call in client.last_tool_calls
            if call["name"] == "verify_command_result"
        ]
        self.assertEqual(len(verify_calls), 1)
        self.assertEqual(
            verify_calls[0]["args"]["result"],
            "Exit code: 0\nstdout:\nok",
        )

    def test_selected_strategy_is_authoritative_after_seed_record(self):
        responses = [
            {
                "choices": [{
                    "message": {
                        "tool_calls": [{
                            "id": "selected-call",
                            "type": "function",
                            "function": {
                                "name": "verify_command_result",
                                "arguments": json.dumps({"result": "", "expected": "Python"}),
                            },
                        }]
                    }
                }]
            },
            {"choices": [{"message": {"content": "done"}}]},
        ]
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(item) for item in responses],
        ) as open_url, patch(
            "gemini_agent.learning.select_verified_strategy",
            return_value="Verified strategy selection: verify_command_result",
        ), patch(
            "gemini_agent.learning.record_verified_experience",
            return_value="Verified experience learned.",
        ) as recorder:
            client = GeminiClient(
                tool_handlers={
                    "record_verified_experience_tool": lambda **kwargs: "Verified experience learned.",
                    "verify_command_result": lambda result, expected: (
                        "Verification: VERIFIED: expected text found: Python"
                        if "Python" in result
                        else "Verification: FAILED: expected text not found: Python"
                    ),
                    "run_command": lambda command: "Exit code: 0\nstdout:\nPython 3.14.6",
                }
            )
            answer = client.ask(
                'First record a verified experience for request "verify a safe command result" '
                'using strategy "verify_command_result" with verification "Verification: VERIFIED: seed." '
                'Then use the normal decision process for request "verify a safe command result". '
                'I have two candidate strategies: "fallback_probe" and "verify_command_result". '
                'Use the verified-experience preference to choose the preferred strategy, then '
                'execute the selected strategy exactly once to verify the goal using command '
                '"python --version" and expected text "Python".'
            )
        self.assertEqual(answer, "done")
        self.assertEqual(
            [call["name"] for call in client.last_tool_calls],
            [
                "select_verified_strategy_tool",
                "record_verified_experience_tool",
                "verify_command_result",
            ],
        )
        verify_call = client.last_tool_calls[-1]
        self.assertEqual(verify_call["args"]["result"], "Exit code: 0\nstdout:\nPython 3.14.6")
        self.assertEqual(open_url.call_count, 2)
        first_payload = json.loads(open_url.call_args_list[0].args[0].data)
        self.assertEqual(
            [tool["function"]["name"] for tool in first_payload["tools"]],
            ["verify_command_result"],
        )
        self.assertEqual(
            first_payload["tool_choice"],
            {"type": "function", "function": {"name": "verify_command_result"}},
        )
        second_payload = json.loads(open_url.call_args_list[1].args[0].data)
        self.assertNotIn("tools", second_payload)
        self.assertNotIn("tool_choice", second_payload)
        recorder.assert_called_once_with(
            "verify a safe command result",
            "verify_command_result",
            "Verification: VERIFIED: expected text found: Python",
            domain="general",
        )

    def test_malformed_run_command_arguments_still_reach_bounded_recovery(self):
        tool_response = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "malformed-run-command",
                        "type": "function",
                        "function": {
                            "name": "run_command",
                            "arguments": "not-json",
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
            side_effect=[FakeResponse(tool_response)],
        ), patch(
            "gemini_agent.tools.run_command",
            side_effect=ValueError("Command is not allowed: dumpsys"),
        ) as run_command:
            client = GeminiClient()
            client.tool_handlers["run_command"] = run_command
            client.tool_handlers["diagnose_command_failure"] = (
                lambda command, error: "Diagnosis: bounded failure."
            )
            client.tool_handlers["recover_command"] = (
                lambda command, expected: "Outcome: VERIFIED\nRecovery succeeded."
            )
            result = client.ask(
                'Use run_command with command "dumpsys -l" and expected text "activity".'
            )

        self.assertIn("Automatic tool recovery:", result)
        run_command.assert_not_called()
        trace = client.last_tool_calls[-1]
        self.assertEqual(trace["name"], "run_command")
        self.assertIn("Automatic tool recovery:", trace["result"])
        self.assertIn("Tool error: Expecting value:", trace["result"])
        self.assertIn("Outcome: VERIFIED", trace["result"])

    def test_compound_run_command_recovery_learning_executes_explicit_command_locally(self):
        request = (
            'First record a verified experience for request "recover a failed Android diagnostic check" '
            'using strategy "run_command" with verification "Verification: VERIFIED: bounded recovery-learning seed." '
            'Then use the normal decision process for request "recover a failed Android diagnostic check". '
            'I have two candidate strategies: "run_command" and "calculator". '
            'Use the verified-experience preference to select the preferred executable strategy. '
            'Execute the selected strategy exactly once with command "dumpsys -l" and expected text "activity". '
            'When it fails, use the generic tool-failure recovery coordinator and its existing bounded recovery path.'
        )
        responses = [
            {
                "choices": [{
                    "message": {
                        "tool_calls": [{
                            "id": "run-command-call",
                            "type": "function",
                            "function": {
                                "name": "run_command",
                                "arguments": json.dumps({"command": "dumpsys -l"}),
                            },
                        }]
                    }
                }]
            },
            {"choices": [{"message": {"content": "recovery complete"}}]},
        ]
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(item) for item in responses],
        ), patch(
            "gemini_agent.learning.select_verified_strategy",
            return_value="Verified strategy selection: run_command",
        ), patch(
            "gemini_agent.learning.record_verified_experience",
            return_value="Verified experience learned.",
        ) as record, patch(
            "gemini_agent.tools.run_command",
            side_effect=ValueError("Command is not allowed: dumpsys"),
        ) as run_command:
            client = GeminiClient()
            client.tool_handlers["run_command"] = run_command
            client.tool_handlers["diagnose_command_failure"] = (
                lambda command, error: "Diagnosis: bounded failure."
            )
            client.tool_handlers["recover_command"] = (
                lambda command, expected: "Outcome: VERIFIED\nRecovery succeeded."
            )
            result = client.ask(request)

        run_command.assert_called_once_with(command="dumpsys -l")
        self.assertEqual(result, "recovery complete")
        trace = next(
            item for item in client.last_tool_calls
            if item.get("name") == "run_command"
        )
        self.assertIn("Automatic tool recovery:", trace["result"])
        self.assertIn("Outcome: VERIFIED", trace["result"])
        self.assertIn("Recovery learning:", trace["result"])
        self.assertGreaterEqual(record.call_count, 2)
        record.assert_any_call(
            "recover a failed Android diagnostic check",
            "recover_command",
            "Outcome: VERIFIED\nRecovery succeeded.",
            domain="general",
        )

    def test_compound_verified_learning_request_stays_in_normal_decision_loop(self):
        request = (
            'First record a verified experience for request "verify a safe command result" '
            'using strategy "verify_command_result" with verification "Verification: VERIFIED: seed." '
            'Then use the normal decision process to choose and execute a strategy.'
        )
        selected = GeminiClient._requested_local_tool([
            {"role": "user", "parts": [{"text": request}]}
        ])
        self.assertNotEqual(selected, "record_verified_experience_tool")

    def test_normal_decision_loop_extracts_goal_from_compound_request(self):
        response = {"choices": [{"message": {"content": "selected"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(response),
        ), patch(
            "gemini_agent.learning.select_verified_strategy",
            return_value="Verified strategy selection: verify_command_result",
        ) as select:
            client = GeminiClient()
            client.ask(
                'First record a verified experience for request "verify a safe command result" '
                'using strategy "verify_command_result" with verification "Verification: VERIFIED: seed." '
                'Then use the normal decision process for request "verify a safe command result". '
                'I have two candidate strategies: "fallback_probe" and "verify_command_result".'
            )
        self.assertEqual(select.call_args.args[0], "verify a safe command result")
        self.assertEqual(
            select.call_args.args[1],
            ["fallback_probe", "verify_command_result"],
        )

    def test_normal_decision_loop_preserves_action_verb_for_verified_experience_matching(self):
        response = {"choices": [{"message": {"content": "selected"}}]}
        with patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"}, clear=True), patch(
            "urllib.request.urlopen", return_value=FakeResponse(response)
        ), patch(
            "gemini_agent.learning.select_verified_strategy",
            return_value="Verified strategy selection: retry_safe"
        ) as select:
            client = GeminiClient()
            client.ask(
                'I need to recover a failed network check. I have two candidate strategies: "fallback_probe" and "retry_safe".'
            )
        self.assertEqual(select.call_args.args[0], "recover a failed network check")
        self.assertEqual(select.call_args.args[1], ["fallback_probe", "retry_safe"])

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

    def test_connection_aborted_returns_clear_provider_error(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=ConnectionAbortedError(103, "Software caused connection abort"),
        ):
            client = GeminiClient()
            with self.assertRaisesRegex(
                RuntimeError, "Connection to Cloudflare failed:.*connection abort"
            ):
                client.ask("test connection handling")

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

    def test_active_goal_forces_selected_action_instead_of_prose_only(self):
        from gemini_agent.goal_next_step import GoalNextStep
        from gemini_agent.goal_state import start_goal_state

        response = {"choices": [{"message": {"content": "I will investigate."}}]}
        prompt = (
            "Create a test artifact. Execute the required actions and verify the result. "
            "Do not ask me to write or modify code manually."
        )
        selector_calls = 0

        def select_once_then_stop(*args, **kwargs):
            nonlocal selector_calls
            selector_calls += 1
            if selector_calls == 1:
                return GoalNextStep(
                    "discover_workspace_executables",
                    "Inspect available build resources before choosing a build strategy.",
                )
            return GoalNextStep("STOP", "The test has observed the selected action.")

        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen", return_value=FakeResponse(response)
        ) as open_url, patch(
            "gemini_agent.goal_next_step.select_goal_next_step",
            side_effect=select_once_then_stop,
        ), patch(
            "gemini_agent.client.verify_goal_completion",
            return_value=__import__(
                "gemini_agent.goal_completion", fromlist=["GoalCompletionObservation"]
            ).GoalCompletionObservation("VERIFIED", "Isolated routing test terminates after selected action."),
        ):
            client = GeminiClient()
            client.goal_state = start_goal_state(
                "Create an Android calculator app",
                "Build and independently verify a functional calculator APK",
            )
            from unittest.mock import Mock

            def observe_discovery(*, request):
                # End this isolated test turn after proving the selected handler
                # ran; the production loop is intentionally allowed to continue
                # while a real goal remains active.
                client.goal_state.status = "COMPLETED"
                return "Executable discovery evidence"

            discovery = Mock(side_effect=observe_discovery)
            client.tool_handlers["discover_workspace_executables"] = discovery
            client.ask(prompt)

        sent = json.loads(open_url.call_args_list[0].args[0].data)
        self.assertEqual(
            [tool["function"]["name"] for tool in sent["tools"]],
            ["discover_workspace_executables"],
        )
        self.assertEqual(
            sent["tool_choice"],
            {
                "type": "function",
                "function": {"name": "discover_workspace_executables"},
            },
        )
        discovery.assert_called_once()
        self.assertTrue(discovery.call_args.kwargs["request"].startswith("Create a test artifact."))

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

    def test_allows_bounded_investigation_beyond_three_tool_rounds(self):
        responses = [
            {"choices": [{"message": {"tool_calls": [{"id": "r1", "type": "function", "function": {"name": "get_hostname", "arguments": {}}}]}}]},
            {"choices": [{"message": {"tool_calls": [{"id": "r2", "type": "function", "function": {"name": "get_system_info", "arguments": {}}}]}}]},
            {"choices": [{"message": {"tool_calls": [{"id": "r3", "type": "function", "function": {"name": "get_cpu_count", "arguments": {}}}]}}]},
            {"choices": [{"message": {"tool_calls": [{"id": "r4", "type": "function", "function": {"name": "get_temp_directory", "arguments": {}}}]}}]},
            {"choices": [{"message": {"content": "Investigation complete.", "tool_calls": []}}]},
        ]
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", side_effect=[FakeResponse(r) for r in responses]) as open_url:
            client = GeminiClient()
            answer = client.ask("Investigate the current runtime context using the available observations and report when complete.")
        self.assertEqual(answer, "Investigation complete.")
        self.assertEqual(open_url.call_count, 5)
