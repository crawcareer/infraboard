"""Templated email rendering + SMTP sending for scheduled email tasks.

render_infradapt_onboarding_email() is pure (no I/O) and safe to call from
a request handler for the create-task preview step.

send_email() talks to the SMTP server and reads its settings from the
process environment (SMTP_HOST/PORT/USERNAME/PASSWORD/USE_TLS, FROM_EMAIL)
rather than Flask's app.config, since it is only ever invoked by the
standalone send_scheduled_emails.py script, not from within a request.
"""

import os
import smtplib
from email.message import EmailMessage


def render_infradapt_onboarding_email(candidate, creator):
    """Return (subject, body) for the Infradapt onboarding request email."""
    start_date = candidate.start_date.strftime("%Y-%m-%d") if candidate.start_date else "TBD"

    subject = f"Onboarding request: {candidate.name}"

    body = (
        "Hi Infradapt Support,\n\n"
        "Please process the onboarding request for the following new hire:\n\n"
        f"Name: {candidate.name}\n"
        f"Start date: {start_date}\n\n"
        f"Point of contact for questions: {creator.name} ({creator.email})\n\n"
        "Thanks,\n"
        f"{creator.name}\n"
    )

    return subject, body


def send_email(to, subject, body, cc=None, reply_to=None):
    """Send a plain-text email via SMTP using settings from the environment."""
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    use_tls = os.environ.get("SMTP_USE_TLS", "true").strip().lower() in ("1", "true", "yes")
    from_email = os.environ["FROM_EMAIL"]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)

    recipients = [to] + ([cc] if cc else [])

    with smtplib.SMTP(host, port) as server:
        if use_tls:
            server.starttls()
        if username and password:
            server.login(username, password)
        server.send_message(msg, to_addrs=recipients)
