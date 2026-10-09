""""Command-line chat loop for the minimal Gemini agent."""

import json

from gemini_agent.client import GeminiClient
from gemini_agent.memory import ConversationMemory


def _print_workflow_execution_evidence(client, answer: str = "") -> None:
    """Show bounded execution evidence, including all tool calls for blocked goals."""
    calls = [
        call for call in getattr(client, "last_tool_calls", [])
        if isinstance(call, dict)
    ]
    normalized_answer = " ".join(str(answer).lower().split())
    blocked_goal_report = any(marker in normalized_answer for marker in (
        "goal progress observation: blocked",
        "environmental blockage",
        "environmental blocker",
        "unresolved blockers",
    ))
    if blocked_goal_report:
        print("\nExecution evidence (recorded goal tool trace):")
        safe_calls = []
        for call in calls:
            args = call.get("args")
            if isinstance(args, dict):
                args = {
                    key: ("[REDACTED]" if any(
                        marker in str(key).lower()
                        for marker in ("token", "password", "secret", "api_key", "authorization")
                    ) else value)
                    for key, value in args.items()
                }
            safe_calls.append({
                "name": call.get("name"),
                "args": args,
                "result": str(call.get("result", ""))[:3000],
            })
        print(json.dumps(safe_calls, ensure_ascii=False, indent=2, default=str)[:16000])
        return
    workflow_tools = {"run_workflow", "run_saved_workflow"}
    for call in calls:
        if call.get("name") not in workflow_tools:
            continue
        tool_name = call["name"]
        result = call.get("result")
        print(f"\nExecution evidence (local {tool_name} result):")
        try:
            evidence = json.loads(result) if isinstance(result, str) else result
            print(json.dumps(evidence, ensure_ascii=False, indent=2))
        except (TypeError, ValueError):
            print(str(result)[:16000])
        return

    # If no workflow was selected, expose the recorded discovery/calculation
    # calls so a valid direct-tool fallback can be audited from the CLI.
    evidence_calls = [
        {"name": call.get("name"), "args": call.get("args"), "result": call.get("result")}
        for call in calls
        if call.get("name") in {"list_saved_workflows", "inspect_saved_workflow", "calculator"}
    ]
    if evidence_calls:
        print("\nExecution evidence (local direct-tool results):")
        print(json.dumps(evidence_calls, ensure_ascii=False, indent=2, default=str)[:16000])


def main() -> None:
    memory = ConversationMemory()
    client = GeminiClient(
        tool_handlers={
            "remember_fact": memory.remember_fact,
            "forget_fact": memory.forget_fact,
            "list_memory": memory.list_memory,
        }
    )
    system_instruction = (
        "You are Nova, a concise personal assistant. Use durable memory and recent "
        "conversation context when answering. When the user tells you a stable personal "
        "fact or preference that should be remembered, use remember_fact. When the user "
        "asks what you remember about them, use list_memory. When the user "
        "asks you to forget a remembered fact, use forget_fact. Do not invent facts about "
        "the user. When arithmetic is needed, use the calculator tool instead of calculating "
        "mentally. For goals involving multiple steps or explicit verification, first call "
        "list_saved_workflows and inspect the returned workflow names and descriptions. "
        "Before selecting a plausible candidate, call inspect_saved_workflow by its exact name "
        "and compare its actual steps and arguments with both its description and the goal. "
        "Execute a saved workflow by exact name only when its real behavior fits; otherwise use "
        "relevant existing tools. Do not invent or save a workflow just to force reuse. "
        "Never claim a workflow ran or a "
        "verification occurred unless the corresponding tool call and result provide "
        "evidence. For multi-action goals, execute every required action, including each "
        "independent verification, as a separate tool call unless a selected workflow "
        "explicitly performs those steps. Before reporting completion, compare each claimed "
        "action with the recorded tool results; if required evidence is missing, perform the "
        "missing action rather than describing it as completed. Report actual workflow step "
        "results when available. For any question "
        "asking for the current date, current time, or current date and time, ALWAYS use "
        "the current_datetime tool. Never use web search, web grounding, or an external "
        "clock for those questions. Treat the current_datetime tool result as authoritative. "
        "For any request to read, create, overwrite, append to, search, or otherwise modify "
        "a local file or directory, you MUST call the relevant filesystem tool. Never claim "
        "that a filesystem action was completed unless the tool was actually called and "
        "returned successfully."
    )
    print("Nova agent ready. Type /exit to quit.")
    while True:
        try:
            prompt = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break
        if prompt.lower() in {"/exit", "/quit"}:
            print("Goodbye.")
            break
        if not prompt:
            continue
        try:
            answer = client.ask(prompt, memory.context(), system_instruction)
            memory.add_exchange(prompt, answer)
            print(f"\nNova: {answer}")
            _print_workflow_execution_evidence(client, answer)
        except RuntimeError as exc:
            print(f"\nError: {exc}")


if __name__ == "__main__":
    main()
