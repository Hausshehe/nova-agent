#!/bin/bash
echo "🧪 Testing Nova Agent..."
echo "1. Testing root access..."
python3 -c "import subprocess; print(subprocess.run(['su', '-c', 'id'], capture_output=True, text=True).stdout)"
echo "2. Testing YouTube clear..."
python3 -c "import subprocess; r=subprocess.run(['su', '-c', 'pm clear com.google.android.youtube'], capture_output=True, text=True); print(r.stdout)"
echo "✅ Tests complete!"
