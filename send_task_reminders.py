"""Sends the daily task-reminder email if it's due: enabled, at or past
the admin-configured send time, and not already sent today.

    python send_task_reminders.py

Intended to run frequently via deploy/onboarding-task-reminders.timer
(e.g. every 5 minutes) as a heartbeat -- same self-gating pattern as
sync_ldap_employees.py, so the timer itself never needs editing when the
admin changes the send time in Admin > Task Reminders.

The actual sending logic lives in app/task_reminders.py, shared with the
Admin > Task Reminders "Send now" button.
"""

from datetime import datetime

from app import create_app
from app.extensions import db
from app.models import TaskReminderSettings
from app.task_reminders import is_due, send_reminders


def main():
    app = create_app()
    with app.app_context():
        settings = TaskReminderSettings.query.first()
        now = datetime.now()

        if not is_due(settings, now):
            print("Not due. Skipping.")
            return

        sent, errors = send_reminders(settings)

        settings.last_sent_date = now.date()
        settings.last_sent_status = "ok" if not errors else "error"
        settings.last_sent_message = "; ".join(errors) if errors else None
        settings.last_sent_recipient_count = sent
        db.session.commit()

        print(f"Sent {sent} reminder(s), {len(errors)} error(s).")
        for error in errors:
            print(f"  - {error}")


if __name__ == "__main__":
    main()
