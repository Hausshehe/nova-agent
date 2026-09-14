from __future__ import annotations

import argparse
import time

from .android_bridge import AndroidBridge
from .deepseek_app_transport import (
    DEEPSEEK_NEW_CHAT_URI,
    DEEPSEEK_PACKAGE,
    DEEPSEEK_SHARE_COMPONENT,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Open DeepSeek, inject a prompt, and dump accessibility observations without sending"
    )
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--poll", type=float, default=0.5)
    args = parser.parse_args()

    bridge = AndroidBridge()
    print("Opening DeepSeek new chat...")
    bridge.open_uri(DEEPSEEK_NEW_CHAT_URI, DEEPSEEK_PACKAGE)

    deadline = time.monotonic() + 10.0
    state = bridge.observe()
    while time.monotonic() < deadline and state.package != DEEPSEEK_PACKAGE:
        time.sleep(0.2)
        state = bridge.observe()

    if state.package != DEEPSEEK_PACKAGE:
        raise RuntimeError(f"DeepSeek did not become active: {state.package!r}")

    print("Injecting prompt. Nova will NOT click Send.")
    bridge.share_text(args.prompt, DEEPSEEK_PACKAGE, DEEPSEEK_SHARE_COMPONENT)

    end = time.monotonic() + args.seconds
    while time.monotonic() < end:
        state = bridge.observe()
        print("\n--- OBSERVATION ---")
        print(f"observation_id={state.observation_id}")
        print(f"package={state.package}")
        print(f"activity={state.activity}")
        print(f"elements={len(state.elements)}")
        for index, element in enumerate(state.elements):
            print(
                f"[{index}] id={element.id!r} text={element.text!r} "
                f"desc={element.content_description!r} clickable={element.clickable} "
                f"enabled={element.enabled} editable={element.editable} "
                f"focused={element.focused} visible={element.visible} "
                f"class={element.class_name!r} bounds={element.bounds!r}"
            )
        time.sleep(args.poll)


if __name__ == "__main__":
    main()
