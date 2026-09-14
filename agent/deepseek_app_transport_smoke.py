from __future__ import annotations

import argparse
import json

from .deepseek_app_responder import DeepSeekAppResponder
from .deepseek_app_transport import DeepSeekAppTransport


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test Nova's DeepSeek Android app transport")
    parser.add_argument(
        "--prompt",
        default=(
            "The current Android mission is only a transport test. "
            "Return a minimal valid JSON object with status=continue, "
            "action.type=none, and explain that the transport is working."
        ),
    )
    args = parser.parse_args()

    transport = DeepSeekAppTransport()
    responder = DeepSeekAppResponder(transport)
    session_id = responder.begin_mission()
    response = responder("LIVE TEST PROMPT:\n" + args.prompt)

    print(f"session_id={session_id}")
    print(json.dumps(response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
