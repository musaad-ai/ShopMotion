"""Database models (SQLAlchemy ORM)."""
from datetime import datetime, timedelta

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(16), nullable=False, default="viewer")  # admin | viewer
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_active(self) -> bool:  # consulted by Flask-Login
        return bool(self.active)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Camera(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    location = db.Column(db.String(64), default="")
    source = db.Column(db.String(256), nullable=False, default="0")  # index, file or RTSP URL
    width = db.Column(db.Integer, default=1280)
    height = db.Column(db.Integer, default=720)
    fps = db.Column(db.Integer, default=30)
    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "location": self.location,
            "source": self.source, "resolution": f"{self.width}x{self.height}",
            "width": self.width, "height": self.height, "fps": self.fps,
            "enabled": self.enabled,
        }


class Zone(db.Model):
    """A rectangular store area. Coordinates are normalised (0-1) so the same
    zone drives both the store map and detections at any camera resolution."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    color = db.Column(db.String(9), default="#667eea")
    x = db.Column(db.Float, nullable=False)
    y = db.Column(db.Float, nullable=False)
    w = db.Column(db.Float, nullable=False)
    h = db.Column(db.Float, nullable=False)

    def contains(self, nx: float, ny: float) -> bool:
        return self.x <= nx <= self.x + self.w and self.y <= ny <= self.y + self.h

    def to_dict(self):
        return {"id": self.id, "name": self.name, "color": self.color,
                "x": self.x, "y": self.y, "w": self.w, "h": self.h}


class Visit(db.Model):
    """One tracked person's stay inside one zone — the unit dwell time is built on."""

    id = db.Column(db.Integer, primary_key=True)
    track_id = db.Column(db.String(32), index=True)
    zone_id = db.Column(db.Integer, db.ForeignKey("zone.id"), index=True)
    camera_id = db.Column(db.Integer, db.ForeignKey("camera.id"))
    entered_at = db.Column(db.DateTime, nullable=False, index=True)
    exited_at = db.Column(db.DateTime)
    dwell_seconds = db.Column(db.Float, default=0)
    zone = db.relationship("Zone")


class TrafficSample(db.Model):
    """Periodic people-count sample: occupancy plus newly-seen visitors."""

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    camera_id = db.Column(db.Integer, db.ForeignKey("camera.id"))
    people_count = db.Column(db.Integer, default=0)
    entries = db.Column(db.Integer, default=0)


class HeatmapCell(db.Model):
    """Accumulated presence per grid cell per day."""

    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Date, nullable=False, index=True)
    gx = db.Column(db.Integer, nullable=False)
    gy = db.Column(db.Integer, nullable=False)
    hits = db.Column(db.Integer, default=0)
    __table_args__ = (db.UniqueConstraint("day", "gx", "gy"),)


class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(16), default="info")  # info | warning | danger
    icon = db.Column(db.String(32), default="fa-circle-info")
    title = db.Column(db.String(128), nullable=False)
    message = db.Column(db.String(256), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    resolved = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {"id": self.id, "level": self.level, "icon": self.icon, "title": self.title,
                "message": self.message, "created_at": self.created_at.isoformat(),
                "resolved": self.resolved}


class Activity(db.Model):
    """Human-readable event feed shown on the dashboard."""

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(16), default="info")  # success | info | warning
    icon = db.Column(db.String(32), default="fa-circle-info")
    title = db.Column(db.String(128), nullable=False)
    message = db.Column(db.String(256), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(128), nullable=False)
    report_type = db.Column(db.String(32), nullable=False)  # traffic | heatmap | dwell | summary
    period_start = db.Column(db.DateTime, nullable=False)
    period_end = db.Column(db.DateTime, nullable=False)
    data_json = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(16), default="completed")
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author = db.relationship("User")

    @property
    def period_last_day(self):
        """``period_end`` is exclusive; this is the last day the report covers."""
        return self.period_end - timedelta(microseconds=1)


class Setting(db.Model):
    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.String(256), nullable=False)

    DEFAULTS = {
        "detection_confidence": "0.5",
        "enable_tracking": "true",
        "enable_recording": "false",
        "recording_path": "recordings/",
        "enable_email_alerts": "false",
        "alert_email": "admin@example.com",
        "data_retention_days": "30",
        "crowd_threshold": "15",
    }

    @classmethod
    def get(cls, key, default=None):
        row = db.session.get(cls, key)
        if row is not None:
            return row.value
        return cls.DEFAULTS.get(key, default)

    @classmethod
    def put(cls, key, value):
        row = db.session.get(cls, key)
        if row is None:
            db.session.add(cls(key=key, value=str(value)))
        else:
            row.value = str(value)

    @classmethod
    def as_dict(cls):
        values = dict(cls.DEFAULTS)
        values.update({r.key: r.value for r in cls.query.all()})
        return values
