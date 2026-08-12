import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))


def _bool_env(name, default="false"):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    _default_db_path = os.path.join(basedir, "instance", "onboarding.db")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "SQLALCHEMY_DATABASE_URI", f"sqlite:///{_default_db_path}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER", os.path.join(basedir, "instance", "uploads")
    )
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25 MB max upload
    ALLOWED_RESUME_EXTENSIONS = {"pdf", "doc", "docx"}

    # Mail / SMTP settings (used by send_daily_summary.py, also exposed here
    # so the whole app has one source of config truth)
    SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "25"))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_USE_TLS = _bool_env("SMTP_USE_TLS", "true")
    FROM_EMAIL = os.environ.get("FROM_EMAIL", "onboarding@example.com")

    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
