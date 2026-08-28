"""Templated email rendering + SMTP sending for scheduled email tasks.

render_infradapt_onboarding_email() is pure (no I/O) and safe to call from
a request handler for the create-task preview step.

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

# Defaults used when no Admin > Email Template row exists yet, or a field
# in it is empty. Placeholders use string.Template's $name syntax (not
# Jinja) deliberately: admins edit this as plain text, and Template.
# safe_substitute() never executes code and never raises on an unknown or
# malformed placeholder -- it just leaves it as literal text, which is a
# much more forgiving failure mode for free-text admin input than Jinja
# rendering (which would also be a code-execution surface) or str.format
# (which raises KeyError on typos and needs literal braces escaped).
DEFAULT_ONBOARDING_EMAIL_SUBJECT = "Onboarding request: $candidate_name"
DEFAULT_ONBOARDING_EMAIL_BODY = (
    "Hi Infradapt Support,\n\n"
    "Please process the onboarding request for the following new hire:\n\n"
    "Name: $candidate_name\n"
    "Start date: $start_date\n\n"
    "Point of contact for questions: $creator_name ($creator_email)\n\n"
    "Thanks,\n"
    "$creator_name\n"
)


def render_onboarding_email_template(
    subject_template, body_template, candidate_name, start_date, creator_name, creator_email
):
    """Substitute $candidate_name/$start_date/$creator_name/$creator_email
    into the given subject/body templates. Pure, no I/O -- used both for
    the real render and for the Admin > Email Template preview."""
    context = {
        "candidate_name": candidate_name,
        "start_date": start_date,
        "creator_name": creator_name,
        "creator_email": creator_email,
    }
    subject = Template(subject_template).safe_substitute(**context)
    body = Template(body_template).safe_substitute(**context)
    return subject, body


def render_infradapt_onboarding_email(candidate, creator):
    """Return (subject, body) for the Infradapt onboarding request email,
    using the admin-configured template (Admin > Email Template) if one is
    saved, falling back to the built-in default otherwise."""
    from app.models import EmailTemplate

    stored = EmailTemplate.query.first()
    subject_template = (
        stored.subject_template if stored and stored.subject_template else DEFAULT_ONBOARDING_EMAIL_SUBJECT
    )
    body_template = stored.body_template if stored and stored.body_template else DEFAULT_ONBOARDING_EMAIL_BODY

    start_date = candidate.start_date.strftime("%Y-%m-%d") if candidate.start_date else "TBD"

    return render_onboarding_email_template(
        subject_template, body_template, candidate.name, start_date, creator.name, creator.email
    )


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
