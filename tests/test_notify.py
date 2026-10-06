from app.extensions import db
from app.models import Setting
from app.services import notify


def test_no_email_when_disabled(app):
    assert notify.send_alert_email(app, "t", "b") is False


def test_no_email_without_smtp_host(app):
    Setting.put("enable_email_alerts", "true")
    db.session.commit()
    app.config["SMTP_HOST"] = ""
    assert notify.send_alert_email(app, "t", "b") is False


def test_email_is_sent_when_configured(app, monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            sent.append(("tls",))

        def login(self, user, password):
            sent.append(("login", user))

        def send_message(self, msg):
            sent.append(("send", msg["To"], msg["Subject"]))

    class InlineThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(notify.threading, "Thread", InlineThread)
    Setting.put("enable_email_alerts", "true")
    Setting.put("alert_email", "manager@example.com")
    db.session.commit()
    app.config.update(SMTP_HOST="smtp.example.com", SMTP_USER="bot", SMTP_PASSWORD="x")

    assert notify.send_alert_email(app, "High traffic detected", "20 people") is True
    assert ("send", "manager@example.com", "[ShopMotion] High traffic detected") in sent
    assert ("login", "bot") in sent
