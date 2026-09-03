#!/usr/bin/env python3
"""
Test the root-enabled agent
"""

from agent.android_bridge import AndroidBridge
from agent.root_bridge_wrapper import RootBridgeWrapper
from agent.llm_reasoning_provider import LLMReasoningProvider
from agent.groq import groq_transport
from agent.navigation import NavigationLoop
from agent.goal_evaluator import GoalEvaluator

def test_clear_youtube():
    """Test clearing YouTube storage"""
    print("🧪 Testing root-enabled Nova Agent...")
    
    # Setup bridge with root wrapper
    bridge = AndroidBridge()
    root_bridge = RootBridgeWrapper(bridge)
    
    # Setup LLM provider
    transport = groq_transport()
    provider = LLMReasoningProvider(transport.complete)
    
    # Create navigation loop
    loop = NavigationLoop(
        bridge=root_bridge,
        planner=provider,
        evaluator=GoalEvaluator(),
        max_steps=3
    )
    
    # Test goal
    goal = "Clear YouTube storage"
    print(f"🎯 Goal: {goal}")
    
    result = loop.run(goal)
    print(f"✅ Result: {result}")
    
    return result

if __name__ == "__main__":
    test_clear_youtube()
