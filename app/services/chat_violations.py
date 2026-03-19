"""
Chat violation tracker — exponential disable for off-topic repeat offenders.

Disable schedule:
  1st offense: warning only
  2nd offense: second warning (stronger)
  3rd:  1 hour
  4th:  24 hours
  5th:  7 days
  6th+: 30 days
"""
from datetime import datetime, timezone, timedelta
from app.models.chat_violation import ChatViolation

DISABLE_SCHEDULE = [
    None,               # 1st: warn only
    None,               # 2nd: second warning (stronger)
    timedelta(hours=1),
    timedelta(hours=24),
    timedelta(days=7),
    timedelta(days=30),
]


def check_user_allowed(user_id: int, session) -> dict:
    """
    Returns {allowed: bool, message: str}.
    Call before processing any chat request.
    """
    v = session.query(ChatViolation).filter_by(user_id=user_id).first()
    if v and v.is_currently_disabled():
        until = v.disabled_until.strftime("%Y-%m-%d %H:%M UTC")
        return {
            "allowed": False,
            "message": f"Chat is disabled for your account until {until} due to repeated off-topic use.",
        }
    return {"allowed": True, "message": ""}


def record_violation(user_id: int, query: str, session) -> dict:
    """
    Record an off-topic violation. Returns the warning/disable message to show the user.
    """
    now = datetime.now(timezone.utc)
    v = session.query(ChatViolation).filter_by(user_id=user_id).first()
    if not v:
        v = ChatViolation(user_id=user_id, violation_count=0)
        session.add(v)

    v.violation_count += 1
    v.last_query = query
    v.last_violation_at = now

    idx = min(v.violation_count - 1, len(DISABLE_SCHEDULE) - 1)
    disable_for = DISABLE_SCHEDULE[idx]

    if disable_for:
        v.disabled_until = now + disable_for
        msg = (
            f"⚠️ This is not a general-purpose AI — it's for hockey stats only. "
            f"Your chat access has been suspended for {_fmt_duration(disable_for)}."
        )
    elif v.violation_count == 1:
        msg = (
            "⚠️ This assistant is for hockey stats questions only. "
            "Please ask about players, teams, games, or stats. "
            "Continued off-topic use will result in a temporary suspension."
        )
    else:
        msg = (
            "⚠️ Final warning — this assistant is for hockey stats only. "
            "Your next off-topic message will result in a temporary suspension."
        )

    session.commit()
    return {"message": msg, "violation_count": v.violation_count, "disabled_until": v.disabled_until}


def _fmt_duration(td: timedelta) -> str:
    if td.days >= 7:
        return f"{td.days // 7} week(s)"
    if td.days >= 1:
        return f"{td.days} day(s)"
    return f"{int(td.total_seconds() // 3600)} hour(s)"
