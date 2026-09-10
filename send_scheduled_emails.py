"""Sends pending automated email tasks (Infradapt Onboarding, Rejection,
Interview Request - Phone/In Person, Offer) whose due date has arrived (or
passed). Runs every 5 minutes via deploy/onboarding-scheduled-emails.timer,
same heartbeat cadence as sync_ldap_employees.py and
send_task_reminders.py -- so a task due "today" sends within a few
minutes rather than waiting for a once-daily run.

No self-gating logic is needed here (unlike those two): each HireEvent's
own email_sent_at is already the per-task completion marker, so running
this frequently just means newly-due tasks get picked up sooner, with no
risk of double-sending.

    python send_scheduled_emails.py

Sends the stored email_subject/email_body verbatim — exactly what the user
previewed and edited when creating the task — rather than re-rendering the
template, so edits made at creation time are preserved. The recipient
("To") is *not* frozen at creation time, though: it's derived here from
the task's type and its candidate's current email address (see
email_task_recipient in app/models.py), matching how the Infradapt
Onboarding type has always resolved its fixed support-desk address.
"""

from datetime import date, datetime

from app import create_app
from app.emailing import send_email
from app.extensions import db
from app.models import HireEvent, EMAIL_TASK_TYPES, EMAIL_TASK_TYPE_LABELS, email_task_recipient


def main():
    app = create_app()
    with app.app_context():
        due_tasks = HireEvent.query.filter(
            HireEvent.task_type.in_(EMAIL_TASK_TYPES),
            HireEvent.status == "pending",
            HireEvent.email_sent_at.is_(None),
            HireEvent.due_date <= date.today(),
        ).all()

        for task in due_tasks:
            to = email_task_recipient(task.task_type, task.candidate)
            if not to:
                label = EMAIL_TASK_TYPE_LABELS.get(task.task_type, task.task_type)
                print(
                    f"Skipping {label} email task {task.id} (candidate {task.candidate_id}): "
                    "no recipient email available (candidate has no email on file)."
                )
                continue

            creator = task.creator
            cc = creator.email if creator else None
            try:
                send_email(
                    to=to,
                    subject=task.email_subject,
                    body=task.email_body,
                    cc=cc,
                    reply_to=cc,
                )
            except Exception as exc:
                print(f"Failed to send email task {task.id} (candidate {task.candidate_id}): {exc}")
                continue

            task.status = "done"
            task.email_sent_at = datetime.utcnow()
            db.session.commit()
            print(f"Sent email task {task.id} (candidate {task.candidate_id}) to {to}.")


if __name__ == "__main__":
    main()
