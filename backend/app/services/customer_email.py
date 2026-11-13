"""Email delivery for customer account verification (standard-library SMTP)."""

import smtplib
from email.message import EmailMessage

from app.core.config import Settings


def send_customer_verification_code(settings: Settings, recipient: str, code: str) -> None:
    """Send a short-lived OTP through a configured SMTP account.

    Gmail users should create an App Password with 2-Step Verification enabled.
    The normal Gmail password is never used or stored.
    """
    username = settings.smtp_username.strip()
    password = settings.smtp_app_password.strip()
    sender = (settings.smtp_from_email or username).strip()
    if not username or not password or not sender:
        raise RuntimeError(
            "Email verification is not configured. Add SMTP_USERNAME, SMTP_APP_PASSWORD "
            "and SMTP_FROM_EMAIL to the backend environment."
        )

    message = EmailMessage()
    message["Subject"] = "Your DisputeIQ verification code"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        f"Your DisputeIQ verification code is {code}.\n\n"
        "It expires in 10 minutes and can be used only once. "
        "If you did not create this account, you can ignore this email."
    )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(message)
