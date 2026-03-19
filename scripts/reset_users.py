#!/usr/bin/env python3
"""
Reset all user data for onboarding testing.
Usage: python scripts/reset_users.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.db import PredSession
from sqlalchemy import text

app = create_app()
with app.app_context():
    s = PredSession()
    tables = [
        'pred_league_standings',
        'pred_results',
        'pred_picks',
        'pred_league_members',
        'pred_leagues',
        'pred_user_captain_claims',
        'pred_user_preferences',
        'pred_user_hb_claims',
        'pred_users',
    ]
    for t in tables:
        r = s.execute(text(f'DELETE FROM {t}'))
        print(f'  {t}: {r.rowcount} rows deleted')
    s.commit()
    print('✅ All user data cleared.')
