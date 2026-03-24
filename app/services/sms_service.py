"""
SMS notification service via Twilio.

Config (in .env):
    TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    TWILIO_AUTH_TOKEN=your_auth_token
    TWILIO_FROM_NUMBER=+1xxxxxxxxxx
"""

import logging
import os

logger = logging.getLogger(__name__)


def send_sms(to_phone: str, message: str, user_id: int | None = None) -> bool:
    """
    Send an SMS via Twilio. Returns True on success, False on failure.
    Silently skips if Twilio is not configured.
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")

    if not all([account_sid, auth_token, from_number]):
        logger.debug("Twilio not configured — skipping SMS")
        return False

    if not to_phone:
        return False

    # Normalize phone — ensure E.164 format
    digits = "".join(c for c in to_phone if c.isdigit())
    if len(digits) == 10:
        digits = "1" + digits
    formatted = f"+{digits}"

    twilio_sid = None
    status = "sent"
    error_msg = None

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        msg = client.messages.create(body=message, from_=from_number, to=formatted)
        twilio_sid = msg.sid
        logger.info(f"SMS sent to {formatted} ({twilio_sid})")
    except Exception as e:
        logger.error(f"SMS failed to {formatted}: {e}")
        status = "failed"
        error_msg = str(e)

    # Log to DB (best-effort — never let logging break the caller)
    try:
        from app.db import PredSession
        from app.models.sms_log import SmsLog
        db = PredSession()
        db.add(SmsLog(
            user_id=user_id,
            to_phone=formatted,
            body=message,
            twilio_sid=twilio_sid,
            status=status,
            error=error_msg,
        ))
        db.commit()
        db.close()
    except Exception as log_err:
        logger.warning(f"Could not log SMS to DB: {log_err}")

    return status == "sent"
