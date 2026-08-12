from datetime import datetime, date

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db

ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"
ROLES = (ROLE_ADMIN, ROLE_MEMBER)

CANDIDATE_STATUSES = (
    "prospect",
    "interviewing",
    "offer",
    "hired",
    "rejected",
    "archived",
)

TIMELINE_TYPES = ("pre_hire", "post_hire")
HIRE_EVENT_STATUSES = ("pending", "done")

TASK_TYPE_MANUAL = "manual"
TASK_TYPE_INFRADAPT_ONBOARDING_EMAIL = "infradapt_onboarding_email"
TASK_TYPES = (TASK_TYPE_MANUAL, TASK_TYPE_INFRADAPT_ONBOARDING_EMAIL)

INFRADAPT_SUPPORT_EMAIL = "getsupport@Infradapt.com"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=ROLE_MEMBER)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    notes = db.relationship("Note", backref="author", lazy="dynamic")
    resumes_uploaded = db.relationship("Resume", backref="uploaded_by_user", lazy="dynamic")
    assigned_events = db.relationship(
        "HireEvent",
        foreign_keys="HireEvent.assigned_to",
        backref="assignee",
        lazy="dynamic",
    )

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

    # --- Task type / templated email tasks ---------------------------------
    # Most HireEvents are plain manual checklist items (task_type="manual").
    # A task_type of TASK_TYPE_INFRADAPT_ONBOARDING_EMAIL instead represents
    # a task whose completion is driven by send_scheduled_emails.py sending
    # the stored email_subject/email_body on the task's due_date, rather
    # than a human toggling it done.
    task_type = db.Column(db.String(30), nullable=False, default=TASK_TYPE_MANUAL)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    email_subject = db.Column(db.String(255), nullable=True)
    email_body = db.Column(db.Text, nullable=True)
    email_sent_at = db.Column(db.DateTime, nullable=True)

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
