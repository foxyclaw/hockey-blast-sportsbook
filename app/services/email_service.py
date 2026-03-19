"""
Email notification service via Gmail SMTP.

Uses Gmail's SMTP server with an App Password (not your regular Gmail password).
To get an App Password:
  1. Go to myaccount.google.com/security
  2. Enable 2-Step Verification if not already on
  3. Search "App passwords" → create one → select "Mail" + "Other"
  4. Copy the 16-char password

Config (in .env):
    GMAIL_ADDRESS=kletskov@gmail.com
    GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx   (16-char app password, spaces ok)
    EMAIL_FROM_NAME=Hockey Blast
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, body_text: str, body_html: str = None) -> bool:
    """
    Send an email via Gmail SMTP.
    Returns True on success, False on failure.
    Silently skips if Gmail is not configured.
    """
    gmail_address = os.getenv("GMAIL_ADDRESS")
    app_password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")
    from_name = os.getenv("EMAIL_FROM_NAME", "Hockey Blast")

    if not gmail_address or not app_password:
        logger.debug("Gmail not configured — skipping email (set GMAIL_ADDRESS + GMAIL_APP_PASSWORD)")
        return False

    if not to_email:
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{gmail_address}>"
        msg["To"] = to_email

        msg.attach(MIMEText(body_text, "plain"))
        if body_html:
            msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(gmail_address, app_password)
            smtp.sendmail(gmail_address, to_email, msg.as_string())

        logger.info(f"Email sent to {to_email}")
        return True

    except Exception as e:
        logger.error(f"Email failed to {to_email}: {e}")
        return False
