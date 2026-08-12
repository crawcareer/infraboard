"""Sends pending Infradapt onboarding request emails whose due date has
arrived (or passed). Intended to run daily via
deploy/onboarding-scheduled-emails.timer, ahead of the existing
onboarding-email.timer.

    python send_scheduled_emails.py

Sends the stored email_subject/email_body verbatim — exactly what the user
previewed and edited when creating the task — rather than re-rendering the
template, so edits made at creation time are preserved.
"""

from datetime import date, datetime

from app import create_app
from app.emailing import send_email
from app.extensions import db
from app.models import HireEvent, TASK_TYPE_INFRADAPT_ONBOARDING_EMAIL, INFRADAPT_SUPPORT_EMAIL


def main():
    app = create_app()
    with app.app_context():
        due_tasks = HireEvent.query.filter(
            HireEvent.task_type == TASK_TYPE_INFRADAPT_ONBOARDING_EMAIL,
            HireEvent.status == "pending",
            HireEvent.email_sent_at.is_(None),
            HireEvent.due_date <= date.today(),
        ).all()

        for task in due_tasks:
            creator = task.creator
            cc = creator.email if creator else None
            try:
                send_email(
                    to=INFRADAPT_SUPPORT_EMAIL,
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
            print(f"Sent email task {task.id} (candidate {task.candidate_id}).")


if __name__ == "__main__":
    main()
