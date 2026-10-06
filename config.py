"""Application configuration.

Values are read from environment variables (or a local ``.env`` file) so the
same code runs in development, testing and Docker without edits.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    # --- Security configuration ---
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me")
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    ALLOW_REGISTRATION = _bool("ALLOW_REGISTRATION", True)

    # --- Database configuration ---
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'shopmotion.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Quick start creates tables directly; set to false to manage the schema with Alembic only.
    AUTO_CREATE_TABLES = _bool("AUTO_CREATE_TABLES", True)

    # --- AI module configuration ---
    YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")
    DETECTOR_BACKEND = os.getenv("DETECTOR_BACKEND", "auto")  # auto | yolo | hog
    TRACKER_BACKEND = os.getenv("TRACKER_BACKEND", "auto")  # auto | deepsort | centroid
    INFERENCE_EVERY_N_FRAMES = int(os.getenv("INFERENCE_EVERY_N_FRAMES", "2"))
    HEATMAP_GRID = (32, 18)  # columns x rows of the accumulated heatmap

    # --- Camera and streaming configuration ---
    STREAM_JPEG_QUALITY = int(os.getenv("STREAM_JPEG_QUALITY", "75"))
    SNAPSHOT_DIR = BASE_DIR / "instance" / "snapshots"
    RECORDING_ROOT = BASE_DIR / "instance"  # relative recording paths live under here

    # --- Email alerts (used when "Enable Email Alerts" is switched on) ---
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_SENDER = os.getenv("SMTP_SENDER", "shopmotion@localhost")
    SMTP_TLS = _bool("SMTP_TLS", True)

    # --- Logging configuration ---
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = BASE_DIR / "instance" / "logs" / "shopmotion.log"


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    LOG_FILE = None
    # Lightweight backends keep the test-suite fast and offline (no weight downloads).
    DETECTOR_BACKEND = "hog"
    TRACKER_BACKEND = "centroid"


config_by_name = {"default": Config, "testing": TestingConfig}
