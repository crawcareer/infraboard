"""Daily task-reminder email engine.

Shared by Admin > Task Reminders' "Send now" button and the standalone
send_task_reminders.py script.
"""

from app.emailing import (
    DEFAULT_TASK_REMINDER_BODY,
    DEFAULT_TASK_REMINDER_SUBJECT,
    format_task_list,
    render_task_reminder_email_template,
    send_email,
)
from app.models import HireEvent, User


def is_due(settings, now):
    """Whether send_task_reminders.py should actually send right now:
    enabled, fully configured, at or past today's send_time, and not
    already sent today."""
    if not settings or not settings.enabled or not settings.website_url or not settings.send_time:
        return False
    if settings.last_sent_date == now.date():
        return False
    try:
        send_hour, send_minute = (int(part) for part in settings.send_time.split(":"))
    except (ValueError, AttributeError):
        return False
    return (now.hour, now.minute) >= (send_hour, send_minute)


def send_reminders(settings):
    """Send the reminder to every active user with 1+ pending assigned
    task -- the same set shown in that user's own "My Tasks" dashboard
    section (app/main.py). Returns (sent_count, [error messages]);
    per-recipient send failures don't abort the rest of the batch."""
    subject_template = settings.subject_template or DEFAULT_TASK_REMINDER_SUBJECT
    body_template = settings.body_template or DEFAULT_TASK_REMINDER_BODY

    users = User.query.filter_by(active=True).order_by(User.name).all()
    sent = 0
    errors = []

    for user in users:
        tasks = (
            HireEvent.query.filter_by(assigned_to=user.id, status="pending")
            .order_by(HireEvent.due_date.is_(None), HireEvent.due_date)
            .all()
        )
        if not tasks:
            continue

        subject, body = render_task_reminder_email_template(
            subject_template,
            body_template,
            employee_name=user.name,
            task_count=len(tasks),
            task_list=format_task_list(tasks),
            website_url=settings.website_url,
        )

        try:
            send_email(to=user.email, subject=subject, body=body)
            sent += 1
        except Exception as exc:
            errors.append(f"{user.email}: {exc}")

    return sent, errors
