#!/bin/bash
# rebuild_and_restart.sh — rebuild frontend + restart Flask dev server (port 5002)
# Usage: ./rebuild_and_restart.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "🏒 Hockey Blast Sportsbook Local Rebuild"
echo "========================================="

# ── 1. Kill existing Flask dev server on port 5002 ──────────────────────────
echo ""
echo "🧹 Cleaning up old processes..."
pkill -f "port=5002" 2>/dev/null || true
sleep 1

# ── 2. Rebuild frontend (ALWAYS rebuild dist) ─────────────────────────────
echo ""
echo "🔨 Rebuilding frontend..."
rm -rf frontend/dist frontend/node_modules/.vite

cd frontend
npm run build 2>&1 | tail -10
cd ..

if [ ! -d "frontend/dist" ]; then
  echo "   ❌ Build failed — dist folder missing"
  exit 1
fi
echo "   ✅ Frontend dist rebuilt."

# ── 3. Run DB migrations (if needed) ───────────────────────────────────────
echo ""
echo "🗄️  Running DB migrations..."
source .venv/bin/activate
if alembic upgrade head 2>&1 | tail -3; then
  echo "   ✅ Migrations complete"
else
  echo "   ⚠️  Migrations may have failed — check output"
fi

# ── 4. Start Flask dev server on port 5002 with SSL ──────────────────────
echo ""
echo "🚀 Starting Flask dev server on https://0.0.0.0:5002"
echo "   Press Ctrl+C to stop"
echo ""

python -c "from app import create_app; app = create_app(); app.run(host='0.0.0.0', port=5002, debug=True, ssl_context='adhoc')"
