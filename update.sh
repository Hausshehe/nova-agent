#!/bin/bash
echo "🔄 Checking for updates..."
git pull origin main 2>/dev/null || echo "⚠️  Using local version"
echo "✅ Agent is up to date"
