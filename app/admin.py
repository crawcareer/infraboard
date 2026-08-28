from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user

from app.auth import admin_required
from app.crypto import encrypt_secret
from app.emailing import (
    DEFAULT_ONBOARDING_EMAIL_SUBJECT,
    DEFAULT_ONBOARDING_EMAIL_BODY,
    render_onboarding_email_template,
)
from app.extensions import db
from app.models import EmailSettings, EmailTemplate, INFRADAPT_SUPPORT_EMAIL

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
@login_required
@admin_required
def index():
    return render_template("admin/index.html")


@admin_bp.route("/email-settings", methods=["GET", "POST"])
@login_required
@admin_required
def email_settings():
    settings = EmailSettings.query.first()

    if request.method == "POST":
        host = request.form.get("smtp_host", "").strip()
        port_raw = request.form.get("smtp_port", "").strip()
        username = request.form.get("smtp_username", "").strip()
        password = request.form.get("smtp_password", "")
        use_tls = request.form.get("smtp_use_tls") == "on"
        from_email = request.form.get("from_email", "").strip()

        error = None
        if not host:
            error = "SMTP host is required."
        elif not from_email:
            error = "From email is required."

        port = 587
        if port_raw:
            try:
                port = int(port_raw)
            except ValueError:
                error = "Port must be a number."

        if error:
            flash(error, "danger")
            return render_template(
                "admin/email_settings.html", settings=settings, form=request.form
            )

        if settings is None:
            settings = EmailSettings()
            db.session.add(settings)

        settings.smtp_host = host
        settings.smtp_port = port
        settings.smtp_username = username or None
        if password:
            settings.smtp_password_encrypted = encrypt_secret(password)
        settings.smtp_use_tls = use_tls
        settings.from_email = from_email
        settings.updated_by = current_user.id
        db.session.commit()

        flash("Email settings saved.", "success")
        return redirect(url_for("admin.email_settings"))

    return render_template("admin/email_settings.html", settings=settings, form=None)


def _sample_preview(subject_template, body_template):
    return render_onboarding_email_template(
        subject_template,
        body_template,
        candidate_name="Jane Doe",
        start_date="2026-03-02",
        creator_name=current_user.name,
        creator_email=current_user.email,
    )


@admin_bp.route("/email-template", methods=["GET", "POST"])
@login_required
@admin_required
def email_template():
    template = EmailTemplate.query.first()

    if request.method == "POST":
        if request.form.get("action") == "reset":
            if template:
                db.session.delete(template)
                db.session.commit()
            flash("Email template reset to default.", "info")
            return redirect(url_for("admin.email_template"))

        subject_template = request.form.get("subject_template", "").strip()
        body_template = request.form.get("body_template", "").strip()

        error = None
        if not subject_template or not body_template:
            error = "Subject and body templates cannot be empty."
        elif len(subject_template) > 255:
            error = "Subject template must be 255 characters or fewer."

        if error:
            flash(error, "danger")
            return render_template(
                "admin/email_template.html",
                subject_template=subject_template,
                body_template=body_template,
                preview=_sample_preview(subject_template, body_template),
                updated=template,
                infradapt_support_email=INFRADAPT_SUPPORT_EMAIL,
            )

        if template is None:
            template = EmailTemplate()
            db.session.add(template)

        template.subject_template = subject_template
        template.body_template = body_template
        template.updated_by = current_user.id
        db.session.commit()

        flash("Email template saved.", "success")
        return redirect(url_for("admin.email_template"))

    subject_template = (
        template.subject_template if template and template.subject_template else DEFAULT_ONBOARDING_EMAIL_SUBJECT
    )
    body_template = template.body_template if template and template.body_template else DEFAULT_ONBOARDING_EMAIL_BODY

    return render_template(
        "admin/email_template.html",
        subject_template=subject_template,
        body_template=body_template,
        preview=_sample_preview(subject_template, body_template),
        updated=template,
        infradapt_support_email=INFRADAPT_SUPPORT_EMAIL,
    )
