#!/usr/bin/env python3
"""
NOVA AGENT v3.0 - AI-Powered Phone Controller
Now with OpenAI integration and smarter commands!
"""

import subprocess
import os
import json
import sys
import re
import time
from datetime import datetime

# Try to import AI libraries
try:
    import openai
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    print("⚠️  OpenAI not installed. Run: pip install openai")

class NovaAgent:
    def __init__(self, api_key=None):
        print("🚀 Nova Agent v3.0 Starting...")
        self.device = self.get_device_info()
        print(f"📱 Device: {self.device}")
        
        # Setup AI
        self.api_key = api_key or os.environ.get('OPENAI_API_KEY')
        if self.api_key and AI_AVAILABLE:
            openai.api_key = self.api_key
            print("🧠 AI Mode: ENABLED")
        else:
            print("🧠 AI Mode: DISABLED (use 'setkey YOUR_API_KEY' to enable)")
        
        self.ensure_root()
        self.command_history = []
        self.app_shortcuts = {
            'youtube': 'com.google.android.youtube',
            'whatsapp': 'com.whatsapp',
            'instagram': 'com.instagram.android',
            'facebook': 'com.facebook.katana',
            'twitter': 'com.twitter.android',
            'telegram': 'org.telegram.messenger',
            'settings': 'com.android.settings',
            'spotify': 'com.spotify.music',
            'chrome': 'com.android.chrome',
            'gmail': 'com.google.android.gm',
        }
    
    def ensure_root(self):
        """Verify root access"""
        try:
            result = subprocess.run(['su', '-c', 'id'], capture_output=True, text=True)
            if 'uid=0' in result.stdout:
                print("✅ Root access confirmed")
                return True
            else:
                print("⚠️  No root access - some features limited")
                return False
        except:
            print("⚠️  Root not available - some features limited")
            return False
    
    def get_device_info(self):
        """Get device info"""
        try:
            result = subprocess.run(['getprop', 'ro.product.model'], capture_output=True, text=True)
            return result.stdout.strip()
        except:
            return "Unknown"
    
    def root_exec(self, command):
        """Execute command with root privileges"""
        try:
            result = subprocess.run(['su', '-c', command], 
                                  capture_output=True, text=True, timeout=30)
            return result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return "", "Command timed out"
    
    def exec_without_root(self, command):
        """Execute without root"""
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
            return result.stdout.strip(), result.stderr.strip()
        except:
            return "", "Command failed"
    
    # ============ APP MANAGEMENT ============
    
    def clear_app(self, package_name):
        """Clear app storage/data"""
        # Check if it's a shortcut
        if package_name in self.app_shortcuts:
            package_name = self.app_shortcuts[package_name]
        
        out, err = self.root_exec(f'pm clear {package_name}')
        if "Success" in out:
            return f"✅ Cleared {package_name}"
        return f"❌ Failed to clear {package_name}: {err}"
    
    def launch_app(self, package_name):
        """Launch an app"""
        if package_name in self.app_shortcuts:
            package_name = self.app_shortcuts[package_name]
        
        out, err = self.root_exec(f'monkey -p {package_name} 1')
        if "Events injected" in out:
            return f"✅ Launched {package_name}"
        return f"❌ Failed to launch: {err}"
    
    def list_apps(self, filter_text=""):
        """List installed apps"""
        out, err = self.root_exec('pm list packages')
        if filter_text:
            out = '\n'.join([line for line in out.split('\n') if filter_text in line])
        # Limit output
        lines = out.split('\n')[:20]
        return '\n'.join(lines) + ("\n..." if len(out.split('\n')) > 20 else "")
    
    def get_app_info(self, package_name):
        """Get app details"""
        if package_name in self.app_shortcuts:
            package_name = self.app_shortcuts[package_name]
        
        out, err = self.root_exec(f'dumpsys package {package_name}')
        lines = out.split('\n')
        info = []
        for line in lines[:30]:
            if 'versionName' in line or 'versionCode' in line or 'firstInstallTime' in line:
                info.append(line.strip())
        return '\n'.join(info) if info else "No info found"
    
    def get_foreground_app(self):
        """Get currently running app"""
        out, err = self.root_exec('dumpsys window | grep mCurrentFocus')
        if out:
            match = re.search(r'([\w.]+)/[\w.]+', out)
            if match:
                return match.group(1)
        return None
    
    # ============ SYSTEM CONTROL ============
    
    def tap(self, x, y):
        """Tap at coordinates"""
        self.root_exec(f'input tap {x} {y}')
        return f"✅ Tapped at ({x}, {y})"
    
    def swipe(self, x1, y1, x2, y2, duration=100):
        """Swipe between coordinates"""
        self.root_exec(f'input swipe {x1} {y1} {x2} {y2} {duration}')
        return f"✅ Swiped from ({x1},{y1}) to ({x2},{y2})"
    
    def type_text(self, text):
        """Type text"""
        self.root_exec(f'input text "{text}"')
        return f"✅ Typed: {text}"
    
    def press_key(self, key_code):
        """Press a system key (BACK=4, HOME=3, MENU=82)"""
        self.root_exec(f'input keyevent {key_code}')
        return f"✅ Key pressed: {key_code}"
    
    def take_screenshot(self):
        """Take screenshot"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"/sdcard/screenshot_{timestamp}.png"
        self.root_exec(f'screencap -p {path}')
        return f"📸 Screenshot saved: {path}"
    
    def record_screen(self, duration=10):
        """Record screen"""
        path = f"/sdcard/screenrecord_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        # Run in background
        self.root_exec(f'screenrecord --time-limit {duration} {path} &')
        return f"🎥 Recording {duration}s saved: {path}"
    
    # ============ SETTINGS CONTROL ============
    
    def get_setting(self, namespace, key):
        """Get system setting"""
        out, err = self.root_exec(f'settings get {namespace} {key}')
        return out if out else "Not found"
    
    def set_setting(self, namespace, key, value):
        """Set system setting"""
        out, err = self.root_exec(f'settings put {namespace} {key} {value}')
        return "✅ Setting updated" if not err else f"❌ Failed: {err}"
    
    # ============ AI COMMANDS ============
    
    def set_api_key(self, api_key):
        """Set OpenAI API key"""
        self.api_key = api_key
        if AI_AVAILABLE:
            openai.api_key = api_key
            return "✅ API key set! AI mode enabled"
        return "❌ OpenAI library not installed"
    
    def process_with_ai(self, command):
        """Process command using AI"""
        if not self.api_key or not AI_AVAILABLE:
            return self.process_natural_language(command)
        
        try:
            system_prompt = f"""You are Nova Agent, an AI that controls an Android phone.
Available actions: clear_app(package), launch_app(package), list_apps(filter), 
tap(x,y), swipe(x1,y1,x2,y2), type_text(text), press_key(code), 
take_screenshot(), record_screen(seconds), get_setting(namespace,key)

Current device: {self.device}
Apps shortcuts: youtube, whatsapp, instagram, facebook, twitter, telegram

Respond with a JSON containing:
{{"action": "action_name", "params": {{"param1": "value"}}, "explanation": "what you're doing"}}
            
Example: "clear YouTube storage" -> {{"action": "clear_app", "params": {{"package_name": "youtube"}}, "explanation": "Clearing YouTube app data"}}
"""
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": command}
                ],
                temperature=0.3
            )
            
            result = response.choices[0].message.content
            # Try to parse JSON
            try:
                data = json.loads(result)
                action = data.get('action')
                params = data.get('params', {})
                explanation = data.get('explanation', '')
                
                print(f"🤖 AI says: {explanation}")
                
                # Execute the action
                if hasattr(self, action):
                    method = getattr(self, action)
                    result = method(**params)
                    return result
                else:
                    return f"❌ Unknown action: {action}"
                    
            except json.JSONDecodeError:
                return f"🤖 AI response: {result}"
                
        except Exception as e:
            return f"❌ AI Error: {str(e)}\nFalling back to local processing..."
    
    def process_natural_language(self, command):
        """Process natural language commands without AI"""
        cmd_lower = command.lower().strip()
        
        # Show shortcuts
        if cmd_lower == "help" or cmd_lower == "?":
            shortcuts = "\n".join([f"  • {name}: {pkg}" for name, pkg in self.app_shortcuts.items()])
            return f"""📋 Available App Shortcuts:
{shortcuts}

Example commands:
  • clear youtube
  • launch settings
  • clear storage for com.google.android.youtube
  • list apps
  • screenshot
  • tap 500 500
  • type Hello World
  • press back
  • record 5
  • setkey YOUR_API_KEY (for AI mode)"""
        
        # Check if it's a shortcut command
        for app_name, pkg in self.app_shortcuts.items():
            if cmd_lower.startswith(f"clear {app_name}"):
                return self.clear_app(pkg)
            if cmd_lower.startswith(f"launch {app_name}") or cmd_lower.startswith(f"open {app_name}"):
                return self.launch_app(pkg)
            if cmd_lower.startswith(f"info {app_name}"):
                return self.get_app_info(pkg)
        
        # Clear storage for package
        if "clear" in cmd_lower and ("storage" in cmd_lower or "data" in cmd_lower):
            match = re.search(r'(?:clear|delete|remove)\s+(?:storage|data)\s+(?:for\s+)?(\S+)', command)
            if match:
                pkg = match.group(1)
                return self.clear_app(pkg)
            return "❌ Please specify app: 'clear youtube' or 'clear com.example.app'"
        
        # Launch app
        if "launch" in cmd_lower or "open" in cmd_lower:
            match = re.search(r'(?:launch|open)\s+(\S+)', command)
            if match:
                pkg = match.group(1)
                return self.launch_app(pkg)
            return "❌ Please specify app package or name"
        
        # List apps
        if "list apps" in cmd_lower or "show apps" in cmd_lower:
            filter_text = ""
            if "filter" in cmd_lower:
                parts = command.split("filter")
                filter_text = parts[1].strip() if len(parts) > 1 else ""
            return self.list_apps(filter_text)
        
        # Screenshot
        if "screenshot" in cmd_lower or "screen" in cmd_lower:
            return self.take_screenshot()
        
        # Record
        if "record" in cmd_lower:
            match = re.search(r'record\s+(\d+)', command)
            duration = int(match.group(1)) if match else 10
            return self.record_screen(duration)
        
        # Tap
        if "tap" in cmd_lower:
            match = re.search(r'tap\s+(\d+)\s+(\d+)', command)
            if match:
                return self.tap(int(match.group(1)), int(match.group(2)))
        
        # Type
        if "type" in cmd_lower:
            match = re.search(r'type\s+(.+)', command)
            if match:
                return self.type_text(match.group(1))
        
        # Key press
        if "press" in cmd_lower:
            keys = {'back': 4, 'home': 3, 'menu': 82, 'recent': 187}
            for key_name, code in keys.items():
                if key_name in cmd_lower:
                    return self.press_key(code)
        
        return "❓ Command not understood. Try 'help' for available commands."
    
    # ============ INTERACTIVE MODE ============
    
    def run(self):
        """Main interactive loop"""
        print("\n" + "="*60)
        print("🤖 Nova Agent v3.0 - AI-Powered Phone Controller")
        print("="*60)
        print("\n💡 Quick Commands:")
        print("  • clear youtube           - Clear YouTube data")
        print("  • launch whatsapp         - Open WhatsApp")
        print("  • screenshot              - Take screenshot")
        print("  • record 10               - Record 10s video")
        print("  • help                    - Show all commands")
        if AI_AVAILABLE:
            print("  • setkey YOUR_KEY        - Enable AI mode")
            print("  • [any natural language] - AI will understand!")
        print("="*60 + "\n")
        
        while True:
            try:
                cmd = input("📱 > ").strip()
                if not cmd:
                    continue
                
                # Save to history
                self.command_history.append(cmd)
                
                if cmd.lower() in ['exit', 'quit', 'q']:
                    print("👋 Goodbye!")
                    break
                
                # Handle API key
                if cmd.lower().startswith("setkey "):
                    key = cmd.split(" ", 1)[1]
                    print(self.set_api_key(key))
                    continue
                
                # Use AI if available
                if self.api_key and AI_AVAILABLE:
                    result = self.process_with_ai(cmd)
                else:
                    result = self.process_natural_language(cmd)
                
                print(f"✅ {result}")
                
            except KeyboardInterrupt:
                print("\n👋 Exiting...")
                break
            except Exception as e:
                print(f"❌ Error: {e}")

if __name__ == "__main__":
    agent = NovaAgent()
    agent.run()
