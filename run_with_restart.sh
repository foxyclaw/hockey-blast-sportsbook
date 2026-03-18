#!/bin/bash
# Auto-restart wrapper for hockey-blast-sportsbook
cd "$(dirname "$0")"
set -a && source .env && set +a
PYTHON=".venv/bin/python"

echo "Starting hockey-blast-sportsbook..."
while true; do
    echo "[$(date)] Starting app on port 5002..."
    $PYTHON -c "
from app import create_app
app = create_app()
app.run(host='0.0.0.0', port=5002, ssl_context=('cert.pem','key.pem'), debug=False, use_reloader=False)
"
    EXIT_CODE=$?
    echo "[$(date)] App exited with code $EXIT_CODE — restarting in 3s..."
    sleep 3
done
