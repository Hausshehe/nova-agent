"""
Root Bridge Wrapper - Extends the Android bridge with root actions
The navigation loop sees this as a normal bridge
"""

from typing import Any, Mapping, Protocol
from .core import Action, ActionType, ExecutionResult, WorldState
from .android_bridge import AndroidBridge
from .root_actions import RootActionHandler


class RootBridgeWrapper:
    """Wraps the AndroidBridge and adds root action support"""
    
    def __init__(self, bridge: AndroidBridge):
        self.bridge = bridge
        self.root_handler = RootActionHandler()
    
    def observe(self) -> WorldState:
        """Delegate observation to the real bridge"""
        return self.bridge.observe()
    
    def execute(self, action: Action) -> ExecutionResult:
        """Execute action - root actions go to root handler, others to bridge"""
        # Check if this is a root action
        root_action_types = ["clear_app", "launch_app", "list_apps", "screenshot"]
        
        if action.type.value in root_action_types:
            # Extract parameters from the action
            params = {}
            if action.target:
                # For backward compatibility, some data might be in target
                if hasattr(action.target, 'package'):
                    params['package'] = action.target.package
                if hasattr(action.target, 'filter_text'):
                    params['filter_text'] = action.target.filter_text
            
            # Execute the root action
            return self.root_handler.execute(action.type.value, params)
        
        # For standard actions, delegate to the bridge
        return self.bridge.execute(action)
    
    def wait_for_fresh_observation(self, previous: WorldState, timeout: float) -> WorldState:
        """Delegate to the real bridge"""
        return self.bridge.wait_for_fresh_observation(previous, timeout)
