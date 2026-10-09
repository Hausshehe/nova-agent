"""Command-line chat loop for the minimal Gemini agent."""

import json

from gemini_agent.client import GeminiClient
from gemini_agent.memory import ConversationMemory


def _print_workflow_execution_evidence(client) -> None:
    """Show locally recorded workflow results, not just the model's narration."""
    workflow_tools = {"run_workflow", "run_saved_workflow"}
    for call in getattr(client, "last_tool_calls", []):
        if not isinstance(call, dict) or call.get("name") not in workflow_tools:
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
        "mentally. For any question asking for the current date, current time, or current "
        "date and time, ALWAYS use the current_datetime tool. Never use web search, web "
        "grounding, or an external clock for those questions. Treat the current_datetime "
        "tool result as authoritative. For any request to read, create, overwrite, append to, "
        "search, or otherwise modify a local file or directory, you MUST call the relevant "
        "filesystem tool. Never claim that a filesystem action was completed unless the "
        "tool was actually called and returned successfully."
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
            _print_workflow_execution_evidence(client)
        except RuntimeError as exc:
            print(f"\nError: {exc}")


if __name__ == "__main__":
    main()
