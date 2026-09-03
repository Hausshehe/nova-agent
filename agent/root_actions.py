"""
Root actions - extend Nova's action types with root-based commands
These become additional options the LLM can choose
"""

from typing import Dict, Any, List, Optional
from .core import Action, ActionType, Target, ExecutionResult
from .root_controller import RootController


class RootActionHandler:
    """Handles root-based actions that the LLM can request"""
    
    def __init__(self):
        self.controller = RootController()
    
    def get_action_descriptions(self) -> List[Dict[str, Any]]:
        """Return descriptions of root actions for the LLM prompt"""
        return [
            {
                "action_type": "clear_app",
                "description": "Clear storage/data for an app. Use when the goal involves clearing, deleting, or resetting app data.",
                "parameters": {
                    "package": "App package name or shortcut. Available shortcuts: youtube, whatsapp, instagram, facebook, twitter, telegram, settings, spotify, chrome, gmail"
                },
                "example": '{"action_type": "clear_app", "package": "youtube", "reason": "User asked to clear YouTube storage"}'
            },
            {
                "action_type": "launch_app",
                "description": "Launch/open an app. Use when the goal involves opening, launching, or starting an app.",
                "parameters": {
                    "package": "App package name or shortcut. Available shortcuts: youtube, whatsapp, instagram, facebook, twitter, telegram, settings, spotify, chrome, gmail"
                },
                "example": '{"action_type": "launch_app", "package": "settings", "reason": "User asked to open settings"}'
            },
            {
                "action_type": "list_apps",
                "description": "List installed apps. Use when the goal asks what apps are installed.",
                "parameters": {
                    "filter_text": "Optional text to filter app names"
                },
                "example": '{"action_type": "list_apps", "filter_text": "google", "reason": "User asked what Google apps are installed"}'
            },
            {
                "action_type": "screenshot",
                "description": "Take a screenshot. Use when the goal involves taking a screenshot or capturing the screen.",
                "parameters": {},
                "example": '{"action_type": "screenshot", "reason": "User asked to take a screenshot"}'
            }
        ]
    
    def execute(self, action_type: str, params: Dict[str, Any]) -> ExecutionResult:
        """Execute a root action"""
        if action_type == "clear_app":
            return self.controller.clear_app(params.get("package", ""))
        elif action_type == "launch_app":
            return self.controller.launch_app(params.get("package", ""))
        elif action_type == "list_apps":
            apps = self.controller.list_apps(params.get("filter_text", ""))
            return ExecutionResult(
                accepted=True,
                changed=True,
                verified=True,
                error=None
            )
        elif action_type == "screenshot":
            path = self.controller.screenshot()
            return ExecutionResult(
                accepted=True,
                changed=True,
                verified=True,
                error=None
            )
        else:
            return ExecutionResult(
                accepted=False,
                changed=False,
                verified=False,
                error=f"Unknown root action: {action_type}"
            )
