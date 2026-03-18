"""
Unified notification service.

Creates a pred_notification record (bell) and optionally fires SMS + email
based on the user's preferences.

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

logger = logging.getLogger(__name__)


def notify_user(db, user_id: int, title: str, body: str = None, url: str = None, notif_type: str = "info") -> None:
    """
    Send a notification to a user via all configured channels:
      1. In-app bell (always — inserts pred_notification row)
      2. SMS (if user has notify_phone set and Twilio configured)
      3. Email (if user has notify_email=True and SendGrid configured)
    """
    from app.models.pred_notification import PredNotification
    from app.models.pred_user_preferences import PredUserPreferences
    from app.models.pred_user import PredUser
    from sqlalchemy import select

    # 1. Always create in-app notification
    notif = PredNotification(
        user_id=user_id,
        type=notif_type,
        title=title,
        body=body,
        link=url,
    )
    db.add(notif)
    db.flush()  # get the id without full commit

    # 2. Fetch user + prefs for SMS/email
    try:
        user = db.get(PredUser, user_id)
        prefs = db.execute(
            select(PredUserPreferences).where(PredUserPreferences.user_id == user_id)
        ).scalar_one_or_none()

        sms_text = f"🏒 {title}"
        if body:
            sms_text += f"\n{body}"
        if url:
            site = "https://sportsbook.hockey-blast.com"
            sms_text += f"\n{site}{url}"

        # SMS
        if prefs and prefs.notify_phone:
            from app.services.sms_service import send_sms
            send_sms(prefs.notify_phone, sms_text)

        # Email
        if user and user.email and (not prefs or prefs.notify_email):
            from app.services.email_service import send_email
            html = f"<p>{body or ''}</p>"
            if url:
                site = "https://sportsbook.hockey-blast.com"
                html += f'<p><a href="{site}{url}">Open Hockey Blast →</a></p>'
            send_email(
                to_email=user.email,
                subject=f"🏒 {title}",
                body_text=sms_text,
                body_html=html,
            )

    except Exception as e:
        logger.error(f"notify_user outer error for user {user_id}: {e}")
