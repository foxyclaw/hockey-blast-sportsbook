"""
Unified notification service.

Notification types (enum) and their external delivery rules:
  fantasy_draft   → SMS + email allowed; immediate if auto-picked, 2min delay if normal turn
  fantasy_scoring → SMS + email allowed; daily digest style, rate-limited (max 1 SMS/hr per user)
  pick_result     → bell only (informational)
  info            → bell only

Rate limiting (SMS):
  - fantasy_draft:   max 1 SMS per user per 30 minutes (drafts can be fast)
  - fantasy_scoring: max 1 SMS per user per 60 minutes
  - all others:      bell only, no SMS

Usage:
    notify_user(db, user_id=42, title="Your turn!", notif_type="fantasy_draft", delay_seconds=0)
"""

import logging
import threading
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

NOTIFY_DELAY_SECONDS    = 600   # 10 min default
DRAFT_NOTIFY_DELAY_SECONDS = 120  # 2 min for draft turn alerts

# Notification type config: { type: { sms: bool, rate_limit_minutes: int } }
NOTIF_TYPE_CONFIG = {
    "fantasy_draft":   {"sms": True,  "rate_limit_minutes": 30},
    "fantasy_scoring": {"sms": True,  "rate_limit_minutes": 60},
    "pick_result":     {"sms": False, "rate_limit_minutes": 0},
    "info":            {"sms": False, "rate_limit_minutes": 0},
}
# Default for unknown types — bell only
_DEFAULT_CONFIG = {"sms": False, "rate_limit_minutes": 0}


def _type_config(notif_type: str) -> dict:
    return NOTIF_TYPE_CONFIG.get(notif_type, _DEFAULT_CONFIG)


def _sms_rate_limited(user_id: int, notif_type: str, db) -> bool:
    """Return True if user already got an SMS for this type within the rate limit window."""
    cfg = _type_config(notif_type)
    if not cfg["sms"] or cfg["rate_limit_minutes"] <= 0:
        return False
    from sqlalchemy import select, func
    from app.models.sms_log import SmsLog
    from datetime import timezone as _tz
    window = datetime.now(_tz.utc) - timedelta(minutes=cfg["rate_limit_minutes"])
    count = db.execute(
        select(func.count(SmsLog.id)).where(
            SmsLog.user_id == user_id,
            SmsLog.status == "sent",
            SmsLog.created_at >= window,
        )
    ).scalar() or 0
    return count > 0


def _send_delayed_external(
    user_id: int,
    notif_type: str,
    sms_text: str,
    email_subject: str,
    email_text: str,
    email_html: str,
    notif_created_at: datetime,
    delay_seconds: int = NOTIFY_DELAY_SECONDS,
) -> None:
    """Wait delay_seconds, then send SMS/email if user hasn't been active and not rate-limited."""
    import time
    time.sleep(delay_seconds)

    cfg = _type_config(notif_type)
    if not cfg["sms"]:
        return  # type doesn't allow external delivery

    from app.db import PredSession
    from app.models.pred_user import PredUser
    from app.models.pred_user_preferences import PredUserPreferences
    from sqlalchemy import select

    db = PredSession()
    try:
        user = db.get(PredUser, user_id)
        if not user:
            return

        # Skip if user was active since notification was created
        if user.last_seen_at and user.last_seen_at > notif_created_at:
            logger.info(f"[notify] Skipping SMS for user {user_id} ({notif_type}): active since notification")
            try:
                from app.models.sms_log import SmsLog
                prefs = db.execute(select(PredUserPreferences).where(PredUserPreferences.user_id == user_id)).scalar_one_or_none()
                phone = prefs.notify_phone if prefs else None
                if phone:
                    digits = "".join(c for c in phone if c.isdigit())
                    formatted = f"+1{digits}" if len(digits) == 10 else f"+{digits}"
                    db.add(SmsLog(user_id=user_id, to_phone=formatted, body=sms_text, status="skipped", error="user was active"))
                    db.commit()
            except Exception:
                pass
            return

        # Rate limit check
        if _sms_rate_limited(user_id, notif_type, db):
            logger.info(f"[notify] SMS rate-limited for user {user_id} ({notif_type})")
            return

        prefs = db.execute(
            select(PredUserPreferences).where(PredUserPreferences.user_id == user_id)
        ).scalar_one_or_none()

        # SMS
        if prefs and prefs.notify_phone:
            from app.services.sms_service import send_sms
            send_sms(prefs.notify_phone, sms_text, user_id=user_id)

        # Email
        if user.email and (not prefs or prefs.notify_email):
            from app.services.email_service import send_email
            send_email(to_email=user.email, subject=email_subject, body_text=email_text, body_html=email_html)

    except Exception as e:
        logger.error(f"[notify] Delayed notify error for user {user_id}: {e}")
    finally:
        db.close()


def notify_user(
    db, user_id: int, title: str, body: str = None, url: str = None,
    notif_type: str = "info", bell_only: bool = False,
    delay_seconds: int | None = None,
) -> None:
    """
    Send a notification to a user.

    1. Always creates in-app bell (pred_notifications row)
    2. For types that allow SMS/email (see NOTIF_TYPE_CONFIG):
       - Fires after delay_seconds (default per type)
       - Skipped if user was active since notification
       - Skipped if rate-limited for this type
    bell_only=True forces no external delivery regardless of type.
    """
    from app.models.pred_notification import PredNotification

    notif = PredNotification(
        user_id=user_id,
        type=notif_type,
        title=title,
        body=body,
        link=url,
    )
    db.add(notif)
    db.flush()

    notif_created_at = notif.created_at or datetime.now(timezone.utc)

    cfg = _type_config(notif_type)
    if bell_only or not cfg["sms"]:
        return  # bell only

    site = "https://sportsbook.hockey-blast.com"
    sms_text = f"🏒 {title}"
    if body:
        sms_text += f"\n{body}"
    if url:
        sms_text += f"\n{site}{url}"

    html = f"<p>{body or ''}</p>"
    if url:
        html += f'<p><a href="{site}{url}">Open Hockey Blast →</a></p>'

    effective_delay = delay_seconds if delay_seconds is not None else NOTIFY_DELAY_SECONDS
    t = threading.Thread(
        target=_send_delayed_external,
        args=(user_id, notif_type, sms_text, f"🏒 {title}", sms_text, html, notif_created_at, effective_delay),
        daemon=True,
    )
    t.start()
