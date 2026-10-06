"""Email notifications for important alerts."""
from __future__ import annotations

import logging
import smtplib
import threading
from email.message import EmailMessage

log = logging.getLogger(__name__)


def build_message(sender: str, recipient: str, title: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = f"[ShopMotion] {title}"
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(f"{title}\n\n{body}\n\n— ShopMotion")
    return msg


def send_alert_email(app, title: str, body: str) -> bool:
    """Send an alert email in the background if email alerts are enabled and SMTP is configured.

    Returns True when a send was scheduled.
    """
    from ..models import Setting

    with app.app_context():
        enabled = Setting.get("enable_email_alerts") == "true"
        recipient = Setting.get("alert_email")
    cfg = app.config
    if not enabled or not recipient:
        return False
    if not cfg.get("SMTP_HOST"):
        log.warning("Email alerts are enabled but SMTP_HOST is not configured")
        return False

    msg = build_message(cfg["SMTP_SENDER"], recipient, title, body)

    def _send():
        try:
            with smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=15) as smtp:
                if cfg["SMTP_TLS"]:
                    smtp.starttls()
                if cfg["SMTP_USER"]:
                    smtp.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
                smtp.send_message(msg)
            log.info("Alert email sent to %s", recipient)
        except Exception:
            log.exception("Failed to send alert email")

    threading.Thread(target=_send, name="alert-email", daemon=True).start()
    return True
