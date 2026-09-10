"""Templated email rendering + SMTP sending for scheduled email tasks.

render_email_task_template() is pure (no I/O) and safe to call from a
request handler for the create-task preview step.

send_email() talks to the SMTP server. Settings come from the admin-managed
EmailSettings row (Admin > Email Settings) when one exists with a host
configured, falling back to the SMTP_HOST/PORT/USERNAME/PASSWORD/USE_TLS
and FROM_EMAIL environment variables otherwise — so installs that haven't
visited the admin page yet keep working off .env unchanged. Both callers
(send_scheduled_emails.py and any future in-request sender) need an active
app context for this, same as before.
"""

import os
import smtplib
from email.message import EmailMessage
from string import Template

from app.crypto import decrypt_secret

# Defaults used per automated email task type (see EMAIL_TASK_TYPES in
# app/models.py) when no Admin > Email Templates row exists for that type
# yet, or a field on it is empty. Placeholders use string.Template's $name
# syntax (not Jinja) deliberately: admins edit this as plain text, and
# Template.safe_substitute() never executes code and never raises on an
# unknown or malformed placeholder -- it just leaves it as literal text,
# a much more forgiving failure mode for free-text admin input than Jinja
# rendering (which would also be a code-execution surface) or str.format
# (which raises KeyError on typos and needs literal braces escaped).
DEFAULT_EMAIL_TEMPLATES = {
    "infradapt_onboarding_email": {
        "subject": "Onboarding request: $candidate_name",
        "body": (
            "Hi Infradapt Support,\n\n"
            "Please process the onboarding request for the following new hire:\n\n"
            "Name: $candidate_name\n"
            "Start date: $start_date\n\n"
            "Point of contact for questions: $creator_name ($creator_email)\n\n"
            "Thanks,\n"
            "$creator_name\n"
        ),
    },
    "rejection_email": {
        "subject": "Update on your application - $candidate_name",
        "body": (
            "Hi $candidate_name,\n\n"
            "Thank you for taking the time to apply for $position and for speaking with "
            "our team.\n\n"
            "After careful consideration, we've decided to move forward with other "
            "candidates for this position. We appreciate your interest and wish you the "
            "best in your search.\n\n"
            "If you have any questions, feel free to reach out.\n\n"
            "Best regards,\n"
            "$creator_name\n"
            "$creator_email\n"
        ),
    },
    "interview_phone_email": {
        "subject": "Interview request: $position",
        "body": (
            "Hi $candidate_name,\n\n"
            "Thank you for applying for $position. We'd like to schedule a phone "
            "interview with you to learn more about your background.\n\n"
            "Please reply with a few times that work well for you in the coming week, "
            "and we'll get something on the calendar.\n\n"
            "Looking forward to speaking with you.\n\n"
            "Best regards,\n"
            "$creator_name\n"
            "$creator_email\n"
        ),
    },
    "interview_in_person_email": {
        "subject": "Interview request: $position",
        "body": (
            "Hi $candidate_name,\n\n"
            "Thank you for applying for $position. We'd like to invite you in for an "
            "in-person interview with our team.\n\n"
            "Please reply with a few times that work well for you in the coming week, "
            "and we'll get something scheduled along with directions to our office.\n\n"
            "Looking forward to meeting you.\n\n"
            "Best regards,\n"
            "$creator_name\n"
            "$creator_email\n"
        ),
    },
    "offer_email": {
        "subject": "Offer of employment: $position",
        "body": (
            "Hi $candidate_name,\n\n"
            "We're excited to offer you the position of $position, with a proposed "
            "start date of $start_date.\n\n"
            "We'll follow up separately with full offer details. In the meantime, "
            "please reach out with any questions.\n\n"
            "Congratulations, and welcome to the team!\n\n"
            "Best regards,\n"
            "$creator_name\n"
            "$creator_email\n"
        ),
    },
}


def apply_email_template(subject_template, body_template, **context):
    """Substitute the given placeholders into subject/body templates via
    string.Template.safe_substitute(). Pure, no I/O -- the shared low-level
    helper behind every admin-editable email template in this app."""
    subject = Template(subject_template).safe_substitute(**context)
    body = Template(body_template).safe_substitute(**context)
    return subject, body


def build_candidate_email_context(candidate, creator):
    """The standard placeholder set for every automated email task type:
    $candidate_name, $start_date, $position, $creator_name, $creator_email."""
    start_date = candidate.start_date.strftime("%Y-%m-%d") if candidate.start_date else "TBD"
    return {
        "candidate_name": candidate.name,
        "start_date": start_date,
        "position": candidate.position or "the position",
        "creator_name": creator.name,
        "creator_email": creator.email,
    }


def render_candidate_email_template(subject_template, body_template, candidate, creator):
    """Substitute the standard candidate/creator placeholders into the
    given subject/body templates. Pure, no I/O -- used both for the real
    render and for the Admin > Email Templates preview."""
    context = build_candidate_email_context(candidate, creator)
    return apply_email_template(subject_template, body_template, **context)


def render_email_task_template(task_type, candidate, creator):
    """Return (subject, body) for an automated email task of this type,
    using the admin-configured template (Admin > Email Templates) for it
    if one is saved, falling back to that type's built-in default
    otherwise."""
    from app.models import EmailTemplate

    stored = EmailTemplate.query.filter_by(task_type=task_type).first()
    defaults = DEFAULT_EMAIL_TEMPLATES[task_type]
    subject_template = stored.subject_template if stored and stored.subject_template else defaults["subject"]
    body_template = stored.body_template if stored and stored.body_template else defaults["body"]

    return render_candidate_email_template(subject_template, body_template, candidate, creator)


# Defaults for the daily task-reminder email (Admin > Task Reminders).
DEFAULT_TASK_REMINDER_SUBJECT = "You have $task_count pending onboarding task(s)"
DEFAULT_TASK_REMINDER_BODY = (
    "Hi $employee_name,\n\n"
    "You have $task_count pending onboarding task(s) assigned to you:\n\n"
    "$task_list\n"
    "View and update these here: $website_url\n"
)


def render_task_reminder_email_template(subject_template, body_template, employee_name, task_count, task_list, website_url):
    """Substitute $employee_name/$task_count/$task_list/$website_url into
    the given subject/body templates. Pure, no I/O -- used both for the
    real render and for the Admin > Task Reminders preview. task_list is a
    pre-formatted multi-line block (string.Template has no loop syntax, so
    the list is built into a single placeholder value rather than the
    template iterating over tasks itself)."""
    return apply_email_template(
        subject_template,
        body_template,
        employee_name=employee_name,
        task_count=task_count,
        task_list=task_list,
        website_url=website_url,
    )


def format_task_list(tasks):
    """Render a list of HireEvent-like objects (title, candidate, due_date)
    into the plain-text block used as the $task_list placeholder value."""
    lines = []
    for task in tasks:
        due = task.due_date.strftime("%Y-%m-%d") if task.due_date else "no due date"
        candidate_name = task.candidate.name if task.candidate else "(unknown candidate)"
        lines.append(f"- {task.title} ({candidate_name}) -- due {due}")
    return "\n".join(lines)


def _get_smtp_config():
    """Resolve SMTP settings: admin-configured EmailSettings row first,
    falling back to environment variables if no row exists (or it has no
    host set yet)."""
    from app.models import EmailSettings

    settings = EmailSettings.query.first()
    if settings and settings.smtp_host:
        return {
            "host": settings.smtp_host,
            "port": settings.smtp_port or 587,
            "username": settings.smtp_username or None,
            "password": decrypt_secret(settings.smtp_password_encrypted),
            "use_tls": settings.smtp_use_tls,
            "from_email": settings.from_email,
        }

    return {
        "host": os.environ.get("SMTP_HOST"),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "username": os.environ.get("SMTP_USERNAME") or None,
        "password": os.environ.get("SMTP_PASSWORD") or None,
        "use_tls": os.environ.get("SMTP_USE_TLS", "true").strip().lower() in ("1", "true", "yes"),
        "from_email": os.environ.get("FROM_EMAIL") or None,
    }


def send_email(to, subject, body, cc=None, reply_to=None):
    """Send a plain-text email via SMTP using the resolved settings."""
    cfg = _get_smtp_config()
    if not cfg["host"] or not cfg["from_email"]:
        raise RuntimeError(
            "Email is not configured. Set it up in Admin > Email Settings "
            "(or the SMTP_HOST/FROM_EMAIL environment variables)."
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from_email"]
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)

    recipients = [to] + ([cc] if cc else [])

    with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
        if cfg["use_tls"]:
            server.starttls()
        if cfg["username"] and cfg["password"]:
            server.login(cfg["username"], cfg["password"])
        server.send_message(msg, to_addrs=recipients)
