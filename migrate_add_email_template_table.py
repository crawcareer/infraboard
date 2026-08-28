"""One-off migration: creates the email_templates table (used by
Admin > Email Template) if it doesn't already exist.

    python migrate_add_email_template_table.py

Same pattern as migrate_add_email_settings_table.py: uses create_app() +
SQLAlchemy (config.py is stable now, so this doesn't need the raw-sqlite3
approach the earlier column-adding scripts used). Manual, one-off --
not wired into create_app() itself, since onboarding.service runs
multiple gunicorn workers and DDL shouldn't run concurrently from several
worker boots.
"""

from app import create_app
from app.extensions import db
from app.models import EmailTemplate


def main():
    app = create_app()
    with app.app_context():
        EmailTemplate.__table__.create(bind=db.engine, checkfirst=True)
    print("email_templates table ensured.")


if __name__ == "__main__":
    main()
