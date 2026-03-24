"""
Unified notification service.

Creates a pred_notification record (bell) immediately, then fires SMS + email
after a delay (10 min) only if the user hasn't been active since the notification.

Usage:
    from app.services.notify_service import notify_user

    notify_user(
        db=pred_session,
        user_id=42,
        title="Your turn to pick!",
        body="Round 3 is open — you have 2.5 min.",
        url="/fantasy/5",          # optional deep link
    )
"""

import logging
import threading
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

NOTIFY_DELAY_SECONDS = 600  # 10 minutes


def _send_delayed_external(
    user_id: int,
    sms_text: str,
    email_subject: str,
    email_text: str,
    email_html: str,
    notif_created_at: datetime,
) -> None:
    """Wait NOTIFY_DELAY_SECONDS, then send SMS/email if user hasn't been active."""
    import time

    time.sleep(NOTIFY_DELAY_SECONDS)

    from app.db import PredSession
    from app.models.pred_user import PredUser
    from app.models.pred_user_preferences import PredUserPreferences
    from sqlalchemy import select

    db = PredSession()
    try:
        user = db.get(PredUser, user_id)
        if not user:
            return

        # If user was seen after the notification was created, they're active — skip
        if user.last_seen_at and user.last_seen_at > notif_created_at:
            logger.info(f"Delayed notify skipped for user {user_id}: active since notification")
            # Log the skip so we have a record
            try:
                from app.models.sms_log import SmsLog
                phone = prefs.notify_phone if prefs else None
                if phone:
                    digits = "".join(c for c in phone if c.isdigit())
                    formatted = f"+1{digits}" if len(digits) == 10 else f"+{digits}"
                    db.add(SmsLog(
                        user_id=user_id,
                        to_phone=formatted,
                        body=sms_text,
                        status="skipped",
                        error="user was active",
                    ))
                    db.commit()
            except Exception:
                pass
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

            send_email(
                to_email=user.email,
                subject=email_subject,
                body_text=email_text,
                body_html=email_html,
            )

    except Exception as e:
        logger.error(f"Delayed notify error for user {user_id}: {e}")
    finally:
        db.close()


def notify_user(
    db, user_id: int, title: str, body: str = None, url: str = None,
    notif_type: str = "info", bell_only: bool = False,
) -> None:
    """
    Send a notification to a user via all configured channels:
      1. In-app bell (always — inserts pred_notification row immediately)
      2. SMS (if user has notify_phone set) — delayed 10 min, skipped if user was active
      3. Email (if user has notify_email=True) — delayed 10 min, skipped if user was active

    bell_only=True: only creates the in-app bell, no SMS/email (e.g. pick result info).
    """
    from app.models.pred_notification import PredNotification

    # 1. Always create in-app notification immediately
    notif = PredNotification(
        user_id=user_id,
        type=notif_type,
        title=title,
        body=body,
        link=url,
    )
    db.add(notif)
    db.flush()  # get created_at without full commit

    notif_created_at = notif.created_at or datetime.now(timezone.utc)

    # 2. Build SMS/email content
    site = "https://sportsbook.hockey-blast.com"
    sms_text = f"🏒 {title}"
    if body:
        sms_text += f"\n{body}"
    if url:
        sms_text += f"\n{site}{url}"

    html = f"<p>{body or ''}</p>"
    if url:
        html += f'<p><a href="{site}{url}">Open Hockey Blast →</a></p>'

    # 3. Fire delayed SMS/email in a background thread (unless bell_only)
    if not bell_only:
        t = threading.Thread(
            target=_send_delayed_external,
            args=(user_id, sms_text, f"🏒 {title}", sms_text, html, notif_created_at),
            daemon=True,
        )
        t.start()
