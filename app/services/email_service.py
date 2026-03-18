"""
Email notification service via SendGrid.

Config (in .env):
    SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxx
    SENDGRID_FROM_EMAIL=noreply@hockey-blast.com
    SENDGRID_FROM_NAME=Hockey Blast
"""

import logging
import os

logger = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, body_text: str, body_html: str = None) -> bool:
    """
    Send an email via SendGrid. Returns True on success, False on failure.
    Silently skips if SendGrid is not configured.
    """
    api_key = os.getenv("SENDGRID_API_KEY")
    from_email = os.getenv("SENDGRID_FROM_EMAIL", "noreply@hockey-blast.com")
    from_name = os.getenv("SENDGRID_FROM_NAME", "Hockey Blast")

    if not api_key:
        logger.debug("SendGrid not configured — skipping email")
        return False

    if not to_email:
        return False

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail, Content, MimeType

        message = Mail(
            from_email=(from_email, from_name),
            to_emails=to_email,
            subject=subject,
        )
        message.add_content(Content(MimeType.text, body_text))
        if body_html:
            message.add_content(Content(MimeType.html, body_html))

        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        logger.info(f"Email sent to {to_email} — status {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"Email failed to {to_email}: {e}")
        return False
