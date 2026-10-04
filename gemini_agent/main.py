"""Command-line chat loop for the minimal Gemini agent."""

from gemini_agent.client import GeminiClient
from gemini_agent.memory import ConversationMemory


def main() -> None:
    client = GeminiClient()
    memory = ConversationMemory()
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
            answer = client.ask(prompt, memory.history)
            memory.add_exchange(prompt, answer)
            print(f"\nGemini: {answer}")
        except RuntimeError as exc:
            print(f"\nError: {exc}")


if __name__ == "__main__":
    main()
