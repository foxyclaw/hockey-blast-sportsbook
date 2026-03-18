#!/bin/bash
# Auto-restart wrapper for hockey-blast-predictions
cd "$(dirname "$0")"
set -a && source .env && set +a
source .venv/bin/activate

echo "Starting hockey-blast-predictions..."
while true; do
    echo "[$(date)] Starting app on port 5002..."
    python -c "
from app import create_app
app = create_app()
app.run(host='0.0.0.0', port=5002, ssl_context=('cert.pem','key.pem'), debug=False, use_reloader=False)
"
    EXIT_CODE=$?
    echo "[$(date)] App exited with code $EXIT_CODE — restarting in 3s..."
    sleep 3
done
