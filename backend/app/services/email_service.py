from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from html import escape

from app.core.config import get_settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


def configured() -> bool:
    settings = get_settings()
    return bool(settings.smtp_host and settings.smtp_from_email)


def require_mailer() -> None:
    if not configured():
        raise AppError(
            "Email is not configured. Set SMTP_HOST, SMTP_FROM_EMAIL, and SMTP credentials.",
            status_code=503,
            code="email_unconfigured",
        )


def _from_header() -> str:
    settings = get_settings()
    return formataddr((settings.smtp_from_name, settings.smtp_from_email))


def _send_sync(to_email: str, subject: str, text: str, html: str) -> None:
    settings = get_settings()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = _from_header()
    msg["To"] = to_email
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    context = ssl.create_default_context()
    if settings.smtp_use_ssl:
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=20, context=context
        )
    else:
        client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
    try:
        client.ehlo()
        if settings.smtp_use_tls and not settings.smtp_use_ssl:
            client.starttls(context=context)
            client.ehlo()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(msg)
    finally:
        try:
            client.quit()
        except Exception:  # noqa: BLE001
            client.close()


async def send_email(to_email: str, subject: str, text: str, html: str) -> None:
    require_mailer()
    try:
        await asyncio.to_thread(_send_sync, to_email, subject, text, html)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("SMTP send failed: %s", type(exc).__name__)
        raise AppError(
            "Could not send email. Try again in a few minutes.",
            status_code=503,
            code="email_send_failed",
        ) from exc


async def send_verification_email(to_email: str, full_name: str, verify_url: str) -> None:
    name = escape(full_name or "there")
    subject = "Verify your Spondon email"
    text = (
        f"Hi {full_name or 'there'},\n\n"
        "Confirm your email to finish setting up Spondon and unlock uploads.\n\n"
        f"{verify_url}\n\n"
        "This link expires in 24 hours. If you did not create an account, ignore this email.\n"
    )
    html = f"""\
<p>Hi {name},</p>
<p>Confirm your email to finish setting up Spondon and unlock uploads.</p>
<p><a href="{escape(verify_url)}">Verify email address</a></p>
<p>This link expires in 24 hours. If you did not create an account, ignore this email.</p>
"""
    await send_email(to_email, subject, text, html)
    logger.info("Verification email sent")


async def send_password_reset_email(to_email: str, full_name: str, reset_url: str) -> None:
    name = escape(full_name or "there")
    subject = "Reset your Spondon password"
    text = (
        f"Hi {full_name or 'there'},\n\n"
        "Use this link to choose a new Spondon password:\n\n"
        f"{reset_url}\n\n"
        "This link expires in 1 hour. If you did not request a reset, ignore this email.\n"
    )
    html = f"""\
<p>Hi {name},</p>
<p>Use this link to choose a new Spondon password.</p>
<p><a href="{escape(reset_url)}">Reset password</a></p>
<p>This link expires in 1 hour. If you did not request a reset, ignore this email.</p>
"""
    await send_email(to_email, subject, text, html)
    logger.info("Password reset email sent")
