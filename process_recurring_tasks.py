"""Resets recurring tasks whose due date has arrived (or passed): rolls
the due date forward by the task's recurrence interval and reverts its
status to pending.

    python process_recurring_tasks.py

Runs once daily via deploy/onboarding-recurring-tasks.timer -- daily
granularity is plenty precise for a feature whose minimum interval is a
month, unlike the other scheduled scripts in this project that need
finer granularity (same-day email sends, an admin-configured
time-of-day). The actual reset logic lives in app/recurring_tasks.py.
"""

from app import create_app
from app.recurring_tasks import process_due_recurring_tasks


def main():
    app = create_app()
    with app.app_context():
        count = process_due_recurring_tasks()
        print(f"Reset {count} recurring task(s).")


if __name__ == "__main__":
    main()
