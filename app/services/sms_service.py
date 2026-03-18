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


def send_sms(to_phone: str, message: str) -> bool:
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

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        client.messages.create(
            body=message,
            from_=from_number,
            to=formatted,
        )
        logger.info(f"SMS sent to {formatted}")
        return True
    except Exception as e:
        logger.error(f"SMS failed to {formatted}: {e}")
        return False
