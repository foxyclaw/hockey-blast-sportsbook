#!/bin/bash
cd "$(dirname "$0")"
set -a && source .env && set +a
PYTHON=".venv/bin/python"
APP_PORT=${PORT:-5002}
echo "Starting hockey-blast-sportsbook on port $APP_PORT (HTTP)..."
while true; do
    echo "[$(date)] Starting app on port $APP_PORT..."
    $PYTHON -c "
import os
from app import create_app
app = create_app()
app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5002)), debug=False, use_reloader=False)
"
    EXIT_CODE=$?
    echo "[$(date)] App exited with code $EXIT_CODE — restarting in 3s..."
    sleep 3
done
