#!/usr/bin/env python3
"""Development server with SSL on port 5002"""
import sys
sys.path.insert(0, '/Users/foxyclaw/.openclaw/workspace/hockey-blast-sportsbook')

from app import create_app

app = create_app()
app.run(host='0.0.0.0', port=5002, debug=True, ssl_context='adhoc')
