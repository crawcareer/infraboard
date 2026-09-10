from datetime import datetime, date

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db

ROLE_ADMIN = "admin"
ROLE_EMPLOYEE = "employee"
ROLES = (ROLE_ADMIN, ROLE_EMPLOYEE)

CANDIDATE_STATUSES = (
    "prospect",
    "interviewing",
    "offer",
    "hired",
    "offboarding",
    "rejected",
    "archived",
)

TIMELINE_TYPES = ("pre_hire", "post_hire", "offboarding")
HIRE_EVENT_STATUSES = ("pending", "done")

RECURRENCE_UNITS = ("months", "years")
TASK_REMINDER_WINDOW_DAYS = 14

TASK_TYPE_MANUAL = "manual"
TASK_TYPE_INFRADAPT_ONBOARDING_EMAIL = "infradapt_onboarding_email"
TASK_TYPE_REJECTION_EMAIL = "rejection_email"
TASK_TYPE_INTERVIEW_PHONE_EMAIL = "interview_phone_email"
TASK_TYPE_INTERVIEW_IN_PERSON_EMAIL = "interview_in_person_email"
TASK_TYPE_OFFER_EMAIL = "offer_email"

# Every automated-email task type. New ones should be added here, to
# EMAIL_TASK_TYPE_LABELS below, and to DEFAULT_EMAIL_TEMPLATES in
# app/emailing.py -- everything else (the create-task form, Admin > Email
# Templates, the sender script) drives off these three.
EMAIL_TASK_TYPES = (
    TASK_TYPE_INFRADAPT_ONBOARDING_EMAIL,
    TASK_TYPE_REJECTION_EMAIL,
    TASK_TYPE_INTERVIEW_PHONE_EMAIL,
    TASK_TYPE_INTERVIEW_IN_PERSON_EMAIL,
    TASK_TYPE_OFFER_EMAIL,
)
TASK_TYPES = (TASK_TYPE_MANUAL,) + EMAIL_TASK_TYPES

EMAIL_TASK_TYPE_LABELS = {
    TASK_TYPE_INFRADAPT_ONBOARDING_EMAIL: "Infradapt Onboarding",
    TASK_TYPE_REJECTION_EMAIL: "Rejection",
    TASK_TYPE_INTERVIEW_PHONE_EMAIL: "Interview Request - Phone",
    TASK_TYPE_INTERVIEW_IN_PERSON_EMAIL: "Interview Request - In Person",
    TASK_TYPE_OFFER_EMAIL: "Offer",
}

INFRADAPT_SUPPORT_EMAIL = "getsupport@Infradapt.com"


def email_task_title(task_type):
    """Task title shown in a candidate's timeline for an automated email
    task of this type."""
    if task_type == TASK_TYPE_INFRADAPT_ONBOARDING_EMAIL:
        return "Send Infradapt onboarding request"
    return f"Send {EMAIL_TASK_TYPE_LABELS.get(task_type, task_type)} email"


def email_task_recipient(task_type, candidate):
    """Who an automated email task's "To" address is: the fixed Infradapt
    support address for that one type, the candidate's own email address
    for every other type (may be None if the candidate has none on file)."""
    if task_type == TASK_TYPE_INFRADAPT_ONBOARDING_EMAIL:
        return INFRADAPT_SUPPORT_EMAIL
    return candidate.email if candidate else None

# Plain many-to-many association: a row's mere existence means "this user
# has this asset" -- there's nothing else to track per the spec (no
# quantity, no serial number, just yes/no), so no extra columns here.
user_assets = db.Table(
    "user_assets",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("asset_id", db.Integer, db.ForeignKey("assets.id"), primary_key=True),
)


class Asset(db.Model):
    """A trackable asset type (Admin > User Asset Inventory), e.g. "Security
    code - Brookside Office". Whether a given user has one is tracked via
    the user_assets association table, not on this row."""

    __tablename__ = "assets"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=ROLE_EMPLOYEE)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # --- Active Directory / LDAP sync ---------------------------------------
    # ldap_dn is both the sync-matching key and the identity used to bind
    # against LDAP at login time (see app/ldap_sync.py). is_ldap_synced
    # controls whether login checks a local password at all vs. always
    # deferring to a live LDAP bind. The *_locked flags mark fields an
    # admin has manually edited via Team -> Edit; sync skips any field
    # that's locked for a given user rather than overwriting it.
    ldap_dn = db.Column(db.String(500), nullable=True)
    ldap_username = db.Column(db.String(255), nullable=True)
    is_ldap_synced = db.Column(db.Boolean, nullable=False, default=False)
    name_locked = db.Column(db.Boolean, nullable=False, default=False)
    email_locked = db.Column(db.Boolean, nullable=False, default=False)
    role_locked = db.Column(db.Boolean, nullable=False, default=False)
    active_locked = db.Column(db.Boolean, nullable=False, default=False)

    notes = db.relationship("Note", backref="author", lazy="dynamic")
    resumes_uploaded = db.relationship("Resume", backref="uploaded_by_user", lazy="dynamic")
    assigned_events = db.relationship(
        "HireEvent",
        foreign_keys="HireEvent.assigned_to",
        backref="assignee",
        lazy="dynamic",
    )
    assets = db.relationship("Asset", secondary=user_assets, backref="users")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == ROLE_ADMIN

    # Flask-Login uses is_active; keep our own `active` column but expose
    # the attribute Flask-Login expects.
    @property
    def is_active(self):
        return self.active

    def __repr__(self):
        return f"<User {self.email}>"


class EmailSettings(db.Model):
    """Singleton row holding admin-configured SMTP settings.

    app/emailing.py prefers this row (when smtp_host is set) over the
    SMTP_*/FROM_EMAIL environment variables, so Admin > Email Settings can
    fully replace editing .env for email configuration.
    """

    __tablename__ = "email_settings"

    id = db.Column(db.Integer, primary_key=True)
    smtp_host = db.Column(db.String(255), nullable=True)
    smtp_port = db.Column(db.Integer, nullable=True, default=587)
    smtp_username = db.Column(db.String(255), nullable=True)
    smtp_password_encrypted = db.Column(db.Text, nullable=True)
    smtp_use_tls = db.Column(db.Boolean, nullable=False, default=True)
    from_email = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    updated_by_user = db.relationship("User", foreign_keys=[updated_by])


class EmailTemplate(db.Model):
    """One row per automated email task type (Admin > Email Templates) --
    Infradapt Onboarding, Rejection, Interview Request (Phone / In Person),
    Offer, keyed by task_type (one of EMAIL_TASK_TYPES above).

    app/emailing.py falls back to that type's built-in default subject/body
    when no row exists for it yet, or a field on it is empty. Editing a
    template only affects tasks created after the save --
    HireEvent.email_subject/email_body are frozen at task-creation time
    and don't change retroactively.
    """

    __tablename__ = "email_templates"

    id = db.Column(db.Integer, primary_key=True)
    task_type = db.Column(db.String(40), unique=True, nullable=False)
    subject_template = db.Column(db.String(255), nullable=True)
    body_template = db.Column(db.Text, nullable=True)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    updated_by_user = db.relationship("User", foreign_keys=[updated_by])


class LdapSettings(db.Model):
    """Singleton row holding the Active Directory / LDAP connection config
    (Admin > Active Directory Integration) and the last sync's outcome.

    Attribute mapping (sAMAccountName/mail/displayName/userAccountControl)
    is fixed to standard AD conventions in app/ldap_sync.py rather than
    configurable here, to keep this form manageable.
    """

    __tablename__ = "ldap_settings"

    id = db.Column(db.Integer, primary_key=True)
    host = db.Column(db.String(255), nullable=True)
    port = db.Column(db.Integer, nullable=True, default=636)
    use_ssl = db.Column(db.Boolean, nullable=False, default=True)
    bind_dn = db.Column(db.String(500), nullable=True)
    bind_password_encrypted = db.Column(db.Text, nullable=True)
    search_base = db.Column(db.String(500), nullable=True)
    user_filter = db.Column(
        db.String(500), nullable=True, default="(&(objectCategory=person)(objectClass=user))"
    )
    sync_interval_minutes = db.Column(db.Integer, nullable=False, default=60)

    last_sync_at = db.Column(db.DateTime, nullable=True)
    last_sync_status = db.Column(db.String(20), nullable=True)
    last_sync_message = db.Column(db.Text, nullable=True)
    last_sync_created = db.Column(db.Integer, nullable=True)
    last_sync_updated = db.Column(db.Integer, nullable=True)
    last_sync_deactivated = db.Column(db.Integer, nullable=True)

    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    updated_by_user = db.relationship("User", foreign_keys=[updated_by])


class TaskReminderSettings(db.Model):
    """Singleton row holding the daily task-reminder email config
    (Admin > Task Reminders): whether it's on, what time it fires, the
    site's public URL (for the link in the email -- send_task_reminders.py
    runs outside any request, so there's no request context to build an
    absolute URL from otherwise), and the editable subject/body template.

    send_time is stored as plain "HH:MM" text rather than a Time column --
    simpler to round-trip through an <input type="time"> form field, and
    the only thing ever done with it is a string/tuple comparison against
    the current server-local time in send_task_reminders.py.

    last_sent_date guards against sending twice in one day: the systemd
    timer runs every few minutes as a heartbeat (same pattern as LDAP
    sync's interval self-gating), and the script only actually sends once
    per calendar date, at or after send_time.
    """

    __tablename__ = "task_reminder_settings"

    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    website_url = db.Column(db.String(500), nullable=True)
    send_time = db.Column(db.String(5), nullable=True, default="08:00")
    subject_template = db.Column(db.String(255), nullable=True)
    body_template = db.Column(db.Text, nullable=True)

    last_sent_date = db.Column(db.Date, nullable=True)
    last_sent_status = db.Column(db.String(20), nullable=True)
    last_sent_message = db.Column(db.Text, nullable=True)
    last_sent_recipient_count = db.Column(db.Integer, nullable=True)

    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    updated_by_user = db.relationship("User", foreign_keys=[updated_by])


class Candidate(db.Model):
    __tablename__ = "candidates"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    position = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(30), nullable=False, default="prospect")
    start_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    resumes = db.relationship(
        "Resume", backref="candidate", lazy="dynamic", cascade="all, delete-orphan"
    )
    notes = db.relationship(
        "Note",
        backref="candidate",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="desc(Note.created_at)",
    )
    hire_events = db.relationship(
        "HireEvent",
        backref="candidate",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="[HireEvent.due_date, HireEvent.sort_order]",
    )

    def pre_hire_events(self):
        return self.hire_events.filter_by(timeline_type="pre_hire")

    def post_hire_events(self):
        return self.hire_events.filter_by(timeline_type="post_hire")

    def offboarding_events(self):
        return self.hire_events.filter_by(timeline_type="offboarding")

    def __repr__(self):
        return f"<Candidate {self.name}>"


class Resume(db.Model):
    __tablename__ = "resumes"

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidates.id"), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_path = db.Column(db.String(500), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Note(db.Model):
    __tablename__ = "notes"

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidates.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class TimelineTemplate(db.Model):
    __tablename__ = "timeline_templates"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    events = db.relationship(
        "TemplateEvent",
        backref="template",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="TemplateEvent.sort_order",
    )


class TemplateEvent(db.Model):
    __tablename__ = "template_events"

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(
        db.Integer, db.ForeignKey("timeline_templates.id"), nullable=False
    )
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    day_offset = db.Column(db.Integer, nullable=False, default=0)
    default_assignee_role = db.Column(db.String(20), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)


class HireEvent(db.Model):
    __tablename__ = "hire_events"

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidates.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending")
    timeline_type = db.Column(db.String(20), nullable=False, default="pre_hire")
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Set only for events generated from a TimelineTemplate (copied from
    # TemplateEvent.day_offset at generation time); None for manually-added
    # or email-task events. Lets a later-added start date backfill due
    # dates on just the template-sourced tasks, without needing the
    # originating template to still exist/match.
    day_offset = db.Column(db.Integer, nullable=True)

    # --- Task type / templated email tasks ---------------------------------
    # Most HireEvents are plain manual checklist items (task_type="manual").
    # Any task_type in EMAIL_TASK_TYPES instead represents a task whose
    # completion is driven by send_scheduled_emails.py sending the stored
    # email_subject/email_body on the task's due_date, rather than a human
    # toggling it done. Recipient is derived at send time from task_type +
    # candidate (see email_task_recipient above), not stored on this row.
    task_type = db.Column(db.String(30), nullable=False, default=TASK_TYPE_MANUAL)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    email_subject = db.Column(db.String(255), nullable=True)
    email_body = db.Column(db.Text, nullable=True)
    email_sent_at = db.Column(db.DateTime, nullable=True)

    # --- Recurrence ----------------------------------------------------
    # Manual tasks only (see app/recurring_tasks.py). When a recurring
    # task's due_date arrives or passes, process_recurring_tasks.py rolls
    # due_date forward by recurrence_interval recurrence_units and resets
    # status back to "pending" -- reset is triggered purely by the
    # calendar, not by completion, and assigned_to carries over
    # untouched. recurrence_interval/_unit are only meaningful when
    # is_recurring is True.
    is_recurring = db.Column(db.Boolean, nullable=False, default=False)
    recurrence_interval = db.Column(db.Integer, nullable=True)
    recurrence_unit = db.Column(db.String(10), nullable=True)

    creator = db.relationship("User", foreign_keys=[created_by])

    @property
    def is_overdue(self):
        return (
            self.status == "pending"
            and self.due_date is not None
            and self.due_date < date.today()
        )

    @property
    def is_due_today(self):
        return (
            self.status == "pending"
            and self.due_date is not None
            and self.due_date == date.today()
        )
