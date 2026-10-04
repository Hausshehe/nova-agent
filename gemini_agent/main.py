"""Command-line chat loop for the minimal Gemini agent."""

from gemini_agent.client import GeminiClient
from gemini_agent.memory import ConversationMemory


def main() -> None:
    memory = ConversationMemory()
    client = GeminiClient(
        tool_handlers={
            "remember_fact": memory.remember_fact,
            "forget_fact": memory.forget_fact,
        }
    )
    system_instruction = (
        "You are Nova, a concise personal assistant. Use durable memory and recent "
        "conversation context when answering. When the user tells you a stable personal "
        "fact or preference that should be remembered, use remember_fact. When the user "
        "asks you to forget a remembered fact, use forget_fact. Do not invent facts about "
        "the user. When arithmetic is needed, use the calculator tool instead of calculating "
        "mentally. For any question asking for the current date, current time, or current "
        "date and time, ALWAYS use the current_datetime tool. Never use web search, web "
        "grounding, or an external clock for those questions. Treat the current_datetime "
        "tool result as authoritative. When web search is enabled, use it for current or "
        "time-sensitive information other than the device's current date and time."
    )
    print("Gemini agent ready. Type /exit to quit.")
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
            for call in client.last_tool_calls:
                args = ", ".join(f"{key}={value!r}" for key, value in call["args"].items())
                print(f"\nTool: {call['name']}({args}) = {call['result']}")
            print(f"\nGemini: {answer}")
            for source in client.last_grounding_sources:
                print(f"Source: {source['title']} - {source['uri']}")
        except RuntimeError as exc:
            print(f"\nError: {exc}")


if __name__ == "__main__":
    main()
