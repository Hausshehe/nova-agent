#!/usr/bin/env python3
"""
NOVA AGENT - Full Root-Based Phone Controller
I will keep improving this - you just run it!
"""

import subprocess
import os
import json
import sys
import time
from datetime import datetime

class NovaAgent:
    def __init__(self):
        print("🚀 Nova Agent v2.0 Starting...")
        print(f"📱 Device: {self.get_device_info()}")
        self.ensure_root()
        
    def ensure_root(self):
        """Verify root access"""
        try:
            result = subprocess.run(['su', '-c', 'id'], capture_output=True, text=True)
            if 'uid=0' in result.stdout:
                print("✅ Root access confirmed")
                return True
            else:
                print("❌ No root access! Exiting...")
                sys.exit(1)
        except:
            print("❌ Root not available")
            sys.exit(1)
    
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
    
    # ============ APP MANAGEMENT ============
    
    def clear_app(self, package_name):
        """Clear app storage/data"""
        out, err = self.root_exec(f'pm clear {package_name}')
        if "Success" in out:
            return f"✅ Cleared {package_name}"
        return f"❌ Failed to clear {package_name}: {err}"
    
    def install_app(self, apk_path):
        """Install an APK"""
        out, err = self.root_exec(f'pm install -r {apk_path}')
        if "Success" in out:
            return f"✅ Installed {apk_path}"
        return f"❌ Install failed: {err}"
    
    def uninstall_app(self, package_name):
        """Uninstall app"""
        out, err = self.root_exec(f'pm uninstall {package_name}')
        if "Success" in out:
            return f"✅ Uninstalled {package_name}"
        return f"❌ Uninstall failed: {err}"
    
    def list_apps(self, filter_text=""):
        """List installed apps"""
        out, err = self.root_exec('pm list packages')
        if filter_text:
            out = '\n'.join([line for line in out.split('\n') if filter_text in line])
        return out[:500] + "..." if len(out) > 500 else out
    
    def get_app_info(self, package_name):
        """Get app details"""
        out, err = self.root_exec(f'dumpsys package {package_name}')
        # Extract key info
        lines = out.split('\n')
        info = []
        for line in lines[:30]:  # First 30 lines
            if 'versionName' in line or 'versionCode' in line or 'firstInstallTime' in line:
                info.append(line.strip())
        return '\n'.join(info) if info else "No info found"
    
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
        """Press a system key"""
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
        self.root_exec(f'screenrecord --time-limit {duration} {path}')
        return f"🎥 Recording saved: {path}"
    
    # ============ SETTINGS CONTROL ============
    
    def get_setting(self, namespace, key):
        """Get system setting"""
        out, err = self.root_exec(f'settings get {namespace} {key}')
        return out if out else "Not found"
    
    def set_setting(self, namespace, key, value):
        """Set system setting"""
        out, err = self.root_exec(f'settings put {namespace} {key} {value}')
        return "✅ Setting updated" if not err else f"❌ Failed: {err}"
    
    # ============ FILE OPERATIONS ============
    
    def list_files(self, path="/sdcard"):
        """List files in directory"""
        out, err = self.root_exec(f'ls -la {path}')
        return out[:500] + "..." if len(out) > 500 else out
    
    def copy_file(self, source, destination):
        """Copy file"""
        out, err = self.root_exec(f'cp -r {source} {destination}')
        return "✅ Copied" if not err else f"❌ Failed: {err}"
    
    def delete_file(self, path):
        """Delete file"""
        out, err = self.root_exec(f'rm -rf {path}')
        return "✅ Deleted" if not err else f"❌ Failed: {err}"
    
    # ============ AI COMMANDS ============
    
    def process_natural_language(self, command):
        """Process natural language commands"""
        command = command.lower().strip()
        
        # Clear storage commands
        if "clear" in command and ("storage" in command or "data" in command):
            import re
            match = re.search(r'(?:clear|delete|remove)\s+(?:storage|data)\s+(?:for\s+)?(\S+)', command)
            if match:
                pkg = match.group(1)
                return self.clear_app(pkg)
            return "❌ Please specify app: 'clear storage for com.example.app'"
        
        # Launch app
        if "launch" in command or "open" in command:
            import re
            match = re.search(r'(?:launch|open)\s+(\S+)', command)
            if match:
                pkg = match.group(1)
                out, err = self.root_exec(f'monkey -p {pkg} 1')
                return "✅ Launched" if "Events injected" in out else f"❌ Failed to launch: {err}"
            return "❌ Please specify app package"
        
        # Screenshot
        if "screenshot" in command:
            return self.take_screenshot()
        
        # Get apps
        if "list apps" in command or "show apps" in command:
            filter_text = ""
            if "filter" in command:
                parts = command.split("filter")
                filter_text = parts[1].strip() if len(parts) > 1 else ""
            return self.list_apps(filter_text)
        
        return "❓ Command not understood. Try: 'clear storage for com.example.app' or 'launch com.example.app'"
    
    # ============ INTERACTIVE MODE ============
    
    def run(self):
        """Main interactive loop"""
        print("\n" + "="*50)
        print("🤖 Nova Agent Interactive Mode")
        print("="*50)
        print("\n📋 Available Commands:")
        print("  • clear storage for [package]  - Clear app data")
        print("  • launch [package]            - Open app")
        print("  • list apps [filter]          - List installed apps")
        print("  • screenshot                  - Take screenshot")
        print("  • record [seconds]            - Record screen")
        print("  • tap [x] [y]                - Tap at coordinates")
        print("  • type [text]                - Type text")
        print("  • settings [namespace] [key]  - Get setting")
        print("  • exit / quit                - Exit agent")
        print("\n💡 Example: 'clear storage for com.google.android.youtube'")
        print("="*50 + "\n")
        
        while True:
            try:
                cmd = input("\n📱 > ").strip()
                if not cmd:
                    continue
                
                if cmd.lower() in ['exit', 'quit', 'q']:
                    print("👋 Goodbye!")
                    break
                
                # Parse simple commands
                parts = cmd.split()
                action = parts[0].lower()
                
                if action == "clear" and len(parts) >= 4 and parts[1] == "storage" and parts[2] == "for":
                    print(self.clear_app(parts[3]))
                
                elif action == "launch" and len(parts) >= 2:
                    print(self.process_natural_language(cmd))
                
                elif action == "list" and len(parts) >= 2:
                    filter_text = parts[2] if len(parts) > 2 else ""
                    print(self.list_apps(filter_text))
                
                elif action == "screenshot":
                    print(self.take_screenshot())
                
                elif action == "record":
                    duration = int(parts[1]) if len(parts) > 1 else 10
                    print(self.record_screen(duration))
                
                elif action == "tap" and len(parts) >= 3:
                    print(self.tap(int(parts[1]), int(parts[2])))
                
                elif action == "type" and len(parts) >= 2:
                    text = ' '.join(parts[1:])
                    print(self.type_text(text))
                
                elif action == "settings" and len(parts) >= 3:
                    print(self.get_setting(parts[1], parts[2]))
                
                else:
                    # Try AI processing
                    result = self.process_natural_language(cmd)
                    print(result)
                    
            except KeyboardInterrupt:
                print("\n👋 Exiting...")
                break
            except Exception as e:
                print(f"❌ Error: {e}")

if __name__ == "__main__":
    agent = NovaAgent()
    agent.run()
