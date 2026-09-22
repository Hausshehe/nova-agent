"""Real-device smoke for semantic plan-intent completion."""

from __future__ import annotations

import argparse
import json
import subprocess
import time

from nova_core.capability_runtime import build_capability_runtime

from agent.android_bridge import AndroidBridge
from nova_core.adapters.android import AndroidBridgeAdapter
from nova_core.models import Goal, RunStatus

PACKAGE_NAME = "com.hausshehe.nova"
MAIN_ACTIVITY = f"{PACKAGE_NAME}/.MainActivity"


def _planning_responder(prompt: str):
    payload = json.loads(prompt.split("PREVIOUS_PLAN_REMAINING:", 1)[1].strip())
    if payload:
        return {"steps": ["Complete Recovery with Recovery Fallback Action"]}
    return {"steps": ["Attempt Recovery Primary Action"]}


def _action_responder(prompt: str):
    payload = json.loads(prompt)
    current = payload["plan"]["current"]
    target_id = (
        f"{PACKAGE_NAME}:id/recovery_fallback"
        if "fallback" in current.casefold()
        else f"{PACKAGE_NAME}:id/recovery_primary"
    )
    return {
        "action_type": "tap",
        "target_id": target_id,
        "reason": current,
    }

