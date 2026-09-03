"""
LLM Reasoning Provider - Updated with root action support
"""

from __future__ import annotations

import json
import os
from typing import Callable, Dict, Any, Optional

from .core import Decision, WorldState
from .reasoning_context import ReasoningContext
from .reasoning_payload import build_reasoning_payload
from .reasoning_response import decision_from_response


class LLMReasoningProvider:
    """LLM-based reasoning provider that can handle root actions"""
    
    def __init__(self, complete_fn: Callable[[str], str]):
        self.complete_fn = complete_fn
        self._last_prompt = ""
        self._last_response = ""
    
    def plan(self, context: ReasoningContext) -> Decision:
        """Generate a decision using the LLM"""
        
        # Build the prompt with root action descriptions
        prompt = self._build_prompt(context)
        self._last_prompt = prompt
        
        try:
            response = self.complete_fn(prompt)
            self._last_response = response
            
            # Parse the response
            decision = decision_from_response(response, context)
            
            # If no valid decision was made, fall back to wait
            if decision is None:
                from .core import Action, ActionType, Decision
                return Decision(
                    action=Action(type=ActionType.WAIT, target=None),
                    rationale="LLM response invalid, waiting"
                )
            
            return decision
            
        except Exception as e:
            # If LLM fails, wait
            from .core import Action, ActionType, Decision
            return Decision(
                action=Action(type=ActionType.WAIT, target=None),
                rationale=f"LLM error: {str(e)}, waiting"
            )
    
    def _build_prompt(self, context: ReasoningContext) -> str:
        """Build the prompt for the LLM with root actions included"""
        
        # Get the UI elements description
        elements_desc = []
        for element in context.current_state.elements[:30]:
            if element.clickable or element.editable or element.scrollable:
                desc = {
                    "id": element.id,
                    "text": element.text,
                    "content_description": element.content_description,
                    "clickable": element.clickable,
                    "enabled": element.enabled,
                    "editable": element.editable,
                    "scrollable": element.scrollable,
                    "class": element.class_name,
                    "visible": element.visible,
                }
                elements_desc.append(desc)
        
        # Build action history
        history_desc = []
        for entry in context.history:
            if isinstance(entry, dict):
                history_desc.append({
                    "action": entry.get("action", {}),
                    "result": entry.get("result", {}),
                })
            else:
                history_desc.append(str(entry))
        
        prompt = f"""You are Nova, an AI agent controlling an Android phone.

GOAL: {context.goal}

CURRENT STATE:
- App: {context.current_state.package}
- Activity: {context.current_state.activity}

UI ELEMENTS:
{json.dumps(elements_desc, indent=2)}

ACTION HISTORY:
{json.dumps(history_desc, indent=2)}

AVAILABLE ACTIONS:
1. click - Click on a UI element
   Requires: target with element_id from UI elements above
2. back - Press the back button
3. wait - Wait for UI to settle

ROOT ACTIONS (system commands):
4. clear_app - Clear app storage/data
   Requires: package (e.g., "youtube", "whatsapp", "com.google.android.youtube")
5. launch_app - Launch/open an app
   Requires: package (e.g., "settings", "youtube", "com.android.settings")
6. list_apps - List installed apps
   Optional: filter_text (e.g., "google")
7. screenshot - Take a screenshot

RESPOND WITH JSON:
{{
    "action_type": "click|back|wait|clear_app|launch_app|list_apps|screenshot",
    "target": {{"element_id": "..."}},  // Required for click
    "package": "...",                    // Required for clear_app/launch_app
    "filter_text": "...",                // Optional for list_apps
    "reason": "Brief explanation of why this action"
}}

Important rules:
- For click, ONLY use element IDs that appear in the UI ELEMENTS above
- Do NOT click elements that are not clickable or not enabled
- For clear_app/launch_app, you can use shortcuts: youtube, whatsapp, instagram, facebook, twitter, telegram, settings, spotify, chrome, gmail
- If you've already tried an action that failed, try a different approach
- If the goal seems to be achieved, choose "wait" and explain why
- A single failed action doesn't mean the goal is impossible
- Consider prerequisites - e.g., to clear an app, you don't need to open it first"""
        
        return prompt


def create_llm_provider(complete_fn: Callable[[str], str]) -> LLMReasoningProvider:
    """Factory function for creating an LLM provider"""
    return LLMReasoningProvider(complete_fn)
