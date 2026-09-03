"""
LLM Reasoning Provider - Pure UI navigation, no root actions
The agent navigates the Android UI like a human user
"""

from __future__ import annotations

import json
import os
from typing import Callable, Dict, Any, Optional

from .core import Decision, WorldState, ActionType
from .reasoning_context import ReasoningContext
from .reasoning_response import decision_from_response


class LLMReasoningProvider:
    """LLM-based reasoning provider - UI navigation only"""
    
    def __init__(self, complete_fn: Callable[[str], str]):
        self.complete_fn = complete_fn
        self._last_prompt = ""
        self._last_response = ""
    
    def plan(self, context: ReasoningContext) -> Decision:
        """Generate a decision using the LLM"""
        prompt = self._build_prompt(context)
        self._last_prompt = prompt
        
        try:
            response = self.complete_fn(prompt)
            self._last_response = response
            decision = decision_from_response(response, context)
            
            if decision is None:
                from .core import Action, ActionType, Decision
                return Decision(
                    action=Action(type=ActionType.WAIT, target=None),
                    rationale="LLM response invalid, waiting"
                )
            return decision
            
        except Exception as e:
            from .core import Action, ActionType, Decision
            return Decision(
                action=Action(type=ActionType.WAIT, target=None),
                rationale=f"LLM error: {str(e)}, waiting"
            )
    
    def _build_prompt(self, context: ReasoningContext) -> str:
        """Build the prompt - UI navigation only"""
        
        current_state = context.state
        
        # Build elements description
        elements_desc = []
        if current_state and hasattr(current_state, 'elements'):
            for element in current_state.elements[:30]:
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
                clean_entry = {}
                for key, value in entry.items():
                    if key == 'result' and hasattr(value, '__dict__'):
                        clean_entry[key] = {
                            'accepted': getattr(value, 'accepted', False),
                            'changed': getattr(value, 'changed', False),
                            'verified': getattr(value, 'verified', False),
                            'error': str(getattr(value, 'error', None))
                        }
                    else:
                        clean_entry[key] = value
                history_desc.append(clean_entry)
            else:
                history_desc.append(str(entry))
        
        package = current_state.package if current_state and hasattr(current_state, 'package') else "unknown"
        activity = current_state.activity if current_state and hasattr(current_state, 'activity') else "unknown"
        
        prompt = f"""You are Nova, an AI agent controlling an Android phone by navigating the UI like a human.

GOAL: {context.goal}

CURRENT STATE:
- App: {package}
- Activity: {activity}

UI ELEMENTS (what's on screen):
{json.dumps(elements_desc, indent=2)}

ACTION HISTORY (what you've already tried):
{json.dumps(history_desc, indent=2)}

**HOW TO NAVIGATE:**
- Click on buttons, icons, and text to navigate
- Use back to go back
- Wait if the screen is loading

**AVAILABLE ACTIONS:**
1. click - Tap on a UI element
   Format: {{"action_type": "click", "target": {{"element_id": "..."}}, "reason": "why"}}
   ONLY use element IDs that appear in the UI ELEMENTS above

2. back - Press the back button
   Format: {{"action_type": "back", "reason": "why"}}

3. wait - Wait for the UI to settle
   Format: {{"action_type": "wait", "reason": "why"}}

**HOW TO CLEAR YOUTUBE STORAGE (EXAMPLE):**
Step 1: Find "Settings" on screen → click it
Step 2: Find "Apps" or "Apps & notifications" → click it
Step 3: Find "YouTube" in the list → click it
Step 4: Find "Storage" → click it
Step 5: Find "Clear Data" or "Clear Storage" → click it

**RULES:**
- ONLY click on elements that are visible and clickable
- If an element is not clickable, look for another way
- If you don't see what you need, try scrolling or going back
- Use small steps - navigate one screen at a time

**RESPOND WITH JSON ONLY:**
{{
    "action_type": "click|back|wait",
    "target": {{"element_id": "..."}},  // Required for click
    "reason": "Why you chose this action"
}}"""
        
        return prompt


def create_llm_provider(complete_fn: Callable[[str], str]) -> LLMReasoningProvider:
    return LLMReasoningProvider(complete_fn)
