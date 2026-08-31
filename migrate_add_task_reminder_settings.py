"""One-off migration: creates the task_reminder_settings table (used by
Admin > Task Reminders) if it doesn't already exist.

    python migrate_add_task_reminder_settings.py

Same idempotent, create_app() + SQLAlchemy pattern as
migrate_add_email_settings_table.py / migrate_add_email_template_table.py.
Not run from create_app() itself: onboarding.service runs multiple
gunicorn workers, and DDL shouldn't run concurrently from several worker
boots.
"""

from app import create_app
from app.extensions import db
from app.models import TaskReminderSettings


def main():
    app = create_app()
    with app.app_context():
        TaskReminderSettings.__table__.create(bind=db.engine, checkfirst=True)
    print("task_reminder_settings table ensured.")


if __name__ == "__main__":
    main()
