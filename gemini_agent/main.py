"""Command-line chat loop for the minimal Gemini agent."""

from gemini_agent.client import GeminiClient


def main() -> None:
    client = GeminiClient()
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
            print(f"\nGemini: {client.ask(prompt)}")
        except RuntimeError as exc:
            print(f"\nError: {exc}")


if __name__ == "__main__":
    main()
