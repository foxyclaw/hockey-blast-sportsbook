#!/bin/bash
# pull_and_deploy.sh — pull latest code, rebuild frontend if needed, restart service
# Usage: ./pull_and_deploy.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "🏒 Hockey Blast Sportsbook Deploy"
echo "================================="

# ── 1. Pull latest from GitHub ─────────────────────────────────────────────
echo ""
echo "📥 Pulling latest code..."
git fetch origin main
BEFORE=$(git rev-parse HEAD)
git pull origin main
AFTER=$(git rev-parse HEAD)

if [ "$BEFORE" = "$AFTER" ]; then
  echo "   Already up to date."
  CHANGED_FILES=""
else
  CHANGED_FILES=$(git diff --name-only "$BEFORE" "$AFTER")
  echo "   Updated: $BEFORE → $AFTER"
  echo "$CHANGED_FILES" | sed 's/^/   • /'
fi

# ── 2. Rebuild frontend if src changed ────────────────────────────────────
FRONTEND_CHANGED=$(echo "$CHANGED_FILES" | grep '^frontend/src/' || true)

if [ -n "$FRONTEND_CHANGED" ] || [ -z "$CHANGED_FILES" ]; then
  if [ -n "$FRONTEND_CHANGED" ]; then
    echo ""
    echo "🔨 Frontend source changed — rebuilding dist..."
  else
    echo ""
    echo "🔨 Building frontend (first deploy or forced)..."
  fi

  # Build in temp dir to avoid permission issues
  BUILD_DIR="/tmp/sb-frontend-deploy"
  rm -rf "$BUILD_DIR"
  # Copy frontend source excluding node_modules and dist (always do clean install)
  rsync -a --exclude=node_modules --exclude=dist "$SCRIPT_DIR/frontend/" "$BUILD_DIR/"

  export PATH="/opt/homebrew/bin:$PATH"
  cd "$BUILD_DIR"
  echo "   Installing dependencies..."
  npm install 2>&1 | tail -3
  if [ $? -ne 0 ]; then
    echo "   ❌ npm install failed — aborting deploy."
    exit 1
  fi

  echo "   Building..."
  npm run build 2>&1 | tail -5
  if [ $? -ne 0 ]; then
    echo "   ❌ npm build failed — aborting deploy."
    exit 1
  fi

  # Copy built dist to prod (requires sudoers entry)
  sudo /bin/cp -r "$BUILD_DIR/dist" "$SCRIPT_DIR/frontend/"
  echo "   ✅ Frontend dist updated."
  cd "$SCRIPT_DIR"
else
  echo ""
  echo "⏭️  No frontend changes — skipping dist rebuild."
fi

# ── 3. Run DB migrations ───────────────────────────────────────────────────
echo ""
echo "🗄️  Running DB migrations..."
DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
if "$DEPLOY_DIR/.venv/bin/alembic" -c "$DEPLOY_DIR/migrations/alembic.ini" upgrade head 2>&1; then
  echo "   ✅ Migrations complete"
else
  echo "   ❌ Migrations failed — check output above"
  exit 1
fi

# ── 4. Restart the service ─────────────────────────────────────────────────
echo ""
echo "🔄 Restarting sportsbook service..."
sudo launchctl kickstart -k system/com.pavelkletskov.flask_sportsbook

sleep 4

# ── 4. Health check ────────────────────────────────────────────────────────
echo ""
echo "🩺 Health check..."
HEALTH=$(curl -s --max-time 5 http://127.0.0.1:5003/api/health 2>/dev/null)
if echo "$HEALTH" | grep -q '"ok"'; then
  echo "   ✅ Service is healthy: $HEALTH"
else
  echo "   ❌ Health check failed: $HEALTH"
  echo "   Check logs: tail -30 /tmp/log_flask_sportsbook_err.log"
  exit 1
fi

echo ""
echo "🎉 Deploy complete!"
