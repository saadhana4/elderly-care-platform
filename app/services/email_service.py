"""Email notification service using smtplib.

Provides safe SMTP delivery with graceful fallback for local development and testing.
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List
from app.config import settings

logger = logging.getLogger(__name__)


def send_email(
    to_email: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
) -> bool:
    """Send an email notification via SMTP or mock logging."""
    if not to_email or "@" not in to_email:
        logger.warning("Invalid or empty recipient email: %s", to_email)
        return False

    # Check if SMTP is configured
    if not settings.SMTP_HOST:
        logger.info(
            "[DEV / MOCK EMAIL] To: %s | Subject: %s\n--- Content ---\n%s\n--- End ---",
            to_email,
            subject,
            body_text,
        )
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to_email

        # Attach plain text version
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        # Attach HTML version if available
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

        # Connect and send
        if settings.SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
            if settings.SMTP_TLS:
                server.starttls()

        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

        server.sendmail(settings.SMTP_FROM, [to_email], msg.as_string())
        server.quit()
        logger.info("Successfully sent email to %s", to_email)
        return True

    except Exception as e:
        logger.error("Failed to send email to %s: %s", to_email, str(e))
        return False


def send_batch_emails(recipients: List[str], subject: str, body_text: str, body_html: Optional[str] = None) -> int:
    """Send notifications to multiple recipients. Returns count of successful deliveries."""
    sent_count = 0
    unique_recipients = set(r.strip() for r in recipients if r and "@" in r)
    for email in unique_recipients:
        if send_email(email, subject, body_text, body_html):
            sent_count += 1
    return sent_count
