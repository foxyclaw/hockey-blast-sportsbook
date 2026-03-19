"""
Application-wide constants.
"""

# Reserved user ID for unauthenticated / anonymous actions.
# A pred_users row with this ID must exist in the DB (seeded at setup).
ANONYMOUS_USER_ID = 0
