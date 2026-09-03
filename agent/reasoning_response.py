"""
Reasoning response - UI navigation only
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .core import Action, ActionType, Target, Decision
from .reasoning_context import ReasoningContext


def decision_from_response(
    response_text: str,
    context: ReasoningContext
) -> Decision:
    """Parse LLM response into a Decision - UI navigation only"""
    
    if isinstance(response_text, dict):
        response_text = json.dumps(response_text)
    
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        data = _extract_from_text(response_text)
    
    action_type_str = data.get("action_type", "wait")
    reason = data.get("reason", data.get("rationale", "LLM decision"))
    
    # Map string to ActionType enum
    action_type_map = {
        "click": ActionType.CLICK,
        "back": ActionType.BACK,
        "wait": ActionType.WAIT,
    }
    
    action_type = action_type_map.get(action_type_str.lower(), ActionType.WAIT)
    
    # Handle click
    if action_type == ActionType.CLICK:
        target_data = data.get("target", {})
        element_id = target_data.get("element_id") if target_data else None
        
        if not element_id:
            # Try to find by text
            target_text = target_data.get("text", "")
            if target_text:
                for element in context.state.elements:
                    if target_text in element.text or target_text in element.content_description:
                        element_id = element.id
                        break
        
        if not element_id:
            return Decision(
                action=Action(type=ActionType.WAIT, target=None),
                rationale=f"Could not find target for click action: {data}"
            )
        
        # Validate the target exists and is clickable
        target_element = None
        for element in context.state.elements:
            if element.id == element_id:
                target_element = element
                break
        
        if not target_element:
            return Decision(
                action=Action(type=ActionType.WAIT, target=None),
                rationale=f"Element {element_id} not found in current state"
            )
        
        if not target_element.clickable:
            return Decision(
                action=Action(type=ActionType.WAIT, target=None),
                rationale=f"Element {element_id} is not clickable"
            )
        
        return Decision(
            action=Action(
                type=ActionType.CLICK,
                target=Target(element_id=element_id)
            ),
            rationale=reason
        )
    
    # Handle back/wait
    if action_type in [ActionType.BACK, ActionType.WAIT]:
        return Decision(
            action=Action(type=action_type, target=None),
            rationale=reason
        )
    
    # Unknown - default to wait
    return Decision(
        action=Action(type=ActionType.WAIT, target=None),
        rationale=f"Unknown action type: {action_type_str}, defaulting to wait"
    )


def _extract_from_text(text: str) -> Dict[str, Any]:
    """Extract action from raw text"""
    data = {"action_type": "wait", "reason": text[:100]}
    text_lower = text.lower()
    
    if "click" in text_lower:
        data["action_type"] = "click"
        import re
        id_match = re.search(r'element_id["\']?\s*[:=]\s*["\']?([\w.]+)', text)
        if id_match:
            data["target"] = {"element_id": id_match.group(1)}
    
    elif "back" in text_lower:
        data["action_type"] = "back"
    
    return data
