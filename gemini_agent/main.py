"""Command-line chat loop for the minimal Gemini agent."""

from gemini_agent.client import GeminiClient
from gemini_agent.memory import ConversationMemory


def main() -> None:
    client = GeminiClient()
    memory = ConversationMemory()
    system_instruction = (
        "You are Nova, a concise personal assistant. Use the conversation history "
        "as memory, answer directly, and do not invent facts about the user. "
        "When arithmetic is needed, use the calculator tool instead of calculating mentally."
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
            answer = client.ask(prompt, memory.history, system_instruction)
            memory.add_exchange(prompt, answer)
            for call in client.last_tool_calls:
                print(f"\nTool: {call['name']}({call['expression']}) = {call['result']}")
            print(f"\nGemini: {answer}")
        except RuntimeError as exc:
            print(f"\nError: {exc}")


if __name__ == "__main__":
    main()
