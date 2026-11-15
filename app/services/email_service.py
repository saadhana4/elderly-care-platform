"""Email notification service using smtplib.

Provides safe SMTP delivery with graceful fallback for local development and testing.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import logger, settings


def send_email(
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> bool:
    """Send an email notification via SMTP or mock logging in development mode.

    Args:
        to_email (str): Recipient email address.
        subject (str): Email subject line.
        body_text (str): Plain-text email content.
        body_html (Optional[str]): Optional HTML formatted content.

    Returns:
        bool: True if sent (or safely mocked), False if delivery failed.
    """
    if not to_email or "@" not in to_email:
        logger.warning("Invalid or empty recipient email: %s", to_email)
        return False

    # Graceful mock fallback when SMTP_HOST is unset
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

        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

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
        logger.info("Successfully dispatched email notification to %s", to_email)
        return True

    except (smtplib.SMTPException, OSError, ConnectionError, Exception) as err:
        logger.error("SMTP transport error delivering to %s: %s", to_email, str(err))
        return False


def send_batch_emails(
    recipients: list[str],
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> int:
    """Send notification email to multiple unique recipients.

    Args:
        recipients (List[str]): List of candidate email addresses.
        subject (str): Email subject line.
        body_text (str): Plain-text email content.
        body_html (Optional[str]): Optional HTML content.

    Returns:
        int: Total number of successfully dispatched emails.
    """
    sent_count: int = 0
    unique_recipients: set[str] = {r.strip() for r in recipients if r and "@" in r}
    for email in unique_recipients:
        if send_email(email, subject, body_text, body_html):
            sent_count += 1
    return sent_count
