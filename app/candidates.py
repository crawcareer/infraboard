import os
import re
import uuid
from datetime import datetime, timedelta

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    current_app,
    send_from_directory,
    abort,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.emailing import render_email_task_template
from app.extensions import db
from app.models import (
    Candidate,
    Resume,
    Note,
    User,
    TimelineTemplate,
    TemplateEvent,
    HireEvent,
    CANDIDATE_STATUSES,
    TIMELINE_TYPES,
    TASK_TYPE_MANUAL,
    RECURRENCE_UNITS,
    EMAIL_TASK_TYPES,
    EMAIL_TASK_TYPE_LABELS,
    email_task_recipient,
    email_task_title,
)

candidates_bp = Blueprint("candidates", __name__, url_prefix="/candidates")


def _allowed_resume(filename):
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in current_app.config["ALLOWED_RESUME_EXTENSIONS"]


_PHONE_CHARS_RE = re.compile(r"^\+?[0-9\s\-.()]+$")


def _valid_phone(phone):
    if not _PHONE_CHARS_RE.match(phone):
        return False
    digit_count = len(re.sub(r"\D", "", phone))
    return 7 <= digit_count <= 15


# --- List / detail / create / edit ---------------------------------------

@candidates_bp.route("/")
@login_required
def list_candidates():
    status_filter = request.args.get("status", "").strip()
    query = Candidate.query
    if status_filter and status_filter in CANDIDATE_STATUSES:
        query = query.filter_by(status=status_filter)
    candidates = query.order_by(Candidate.created_at.desc()).all()
    return render_template(
        "candidates/list.html", candidates=candidates, status_filter=status_filter
    )


@candidates_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_candidate():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        position = request.form.get("position", "").strip()
        status = request.form.get("status", "prospect")
        start_date_raw = request.form.get("start_date", "").strip()

        error = None
        if not name:
            error = "Name is required."
        elif phone and not _valid_phone(phone):
            error = "Phone number must contain 7-15 digits, optionally with +, spaces, dashes, dots, or parentheses."
        elif status not in CANDIDATE_STATUSES:
            error = "Invalid status."

        start_date = None
        if start_date_raw:
            try:
                start_date = datetime.strptime(start_date_raw, "%Y-%m-%d").date()
            except ValueError:
                error = "Start date must be a valid date."

        if error:
            flash(error, "danger")
            return render_template("candidates/form.html", candidate=None, form=request.form)

        candidate = Candidate(
            name=name,
            email=email or None,
            phone=phone or None,
            position=position or None,
            status=status,
            start_date=start_date,
        )
        db.session.add(candidate)
        db.session.commit()
        flash(f"Candidate {name} created.", "success")

        resume_files = request.files.getlist("resume_file")
        if any(f and f.filename for f in resume_files):
            saved = _save_resumes(candidate, resume_files)
            if saved:
                flash(f"Uploaded {saved} resume file(s).", "success")

        if status == "hired":
            _instantiate_timeline(candidate, "Pre-Hire", "pre_hire")
            _instantiate_timeline(candidate, "Post-Hire", "post_hire")
            db.session.commit()

        return redirect(url_for("candidates.detail", candidate_id=candidate.id))

    return render_template("candidates/form.html", candidate=None, form={})


@candidates_bp.route("/<int:candidate_id>")
@login_required
def detail(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    users = User.query.filter_by(active=True).order_by(User.name).all()
    pre_hire = candidate.pre_hire_events().all()
    post_hire = candidate.post_hire_events().all()
    offboarding = candidate.offboarding_events().all()
    notes = candidate.notes.all()
    resumes = candidate.resumes.order_by(Resume.uploaded_at.desc()).all()
    has_templates = TimelineTemplate.query.count() > 0
    return render_template(
        "candidates/detail.html",
        candidate=candidate,
        users=users,
        pre_hire=pre_hire,
        post_hire=post_hire,
        offboarding=offboarding,
        notes=notes,
        resumes=resumes,
        has_templates=has_templates,
    )


@candidates_bp.route("/<int:candidate_id>/edit", methods=["GET", "POST"])
@login_required
def edit_candidate(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        position = request.form.get("position", "").strip()
        status = request.form.get("status", "prospect")
        start_date_raw = request.form.get("start_date", "").strip()

        error = None
        if not name:
            error = "Name is required."
        elif phone and not _valid_phone(phone):
            error = "Phone number must contain 7-15 digits, optionally with +, spaces, dashes, dots, or parentheses."
        elif status not in CANDIDATE_STATUSES:
            error = "Invalid status."

        start_date = None
        if start_date_raw:
            try:
                start_date = datetime.strptime(start_date_raw, "%Y-%m-%d").date()
            except ValueError:
                error = "Start date must be a valid date."

        if error:
            flash(error, "danger")
            return render_template("candidates/form.html", candidate=candidate, form=request.form)

        was_hired = candidate.status == "hired"
        had_start_date = candidate.start_date is not None
        candidate.name = name
        candidate.email = email or None
        candidate.phone = phone or None
        candidate.position = position or None
        candidate.status = status
        candidate.start_date = start_date
        db.session.commit()
        flash(f"Candidate {name} updated.", "success")

        if status == "hired" and not was_hired:
            # Moving a candidate to "hired" automatically instantiates their
            # Pre-Hire / Post-Hire timelines from the current templates.
            pre_created = _instantiate_timeline(candidate, "Pre-Hire", "pre_hire")
            post_created = _instantiate_timeline(candidate, "Post-Hire", "post_hire")
            db.session.commit()
            if pre_created or post_created:
                flash(
                    f"Status changed to hired — generated {pre_created} pre-hire "
                    f"and {post_created} post-hire timeline events.",
                    "info",
                )
            else:
                flash(
                    "Status changed to hired, but no timeline templates exist "
                    "yet to generate events from.",
                    "warning",
                )
        elif not had_start_date and start_date is not None:
            # A start date was just added for the first time to a candidate
            # that already has template-generated events (created back when
            # there was no start date, so their due dates are still blank).
            # Backfill due dates on just those events, using each one's
            # stored day_offset — manually-added events (day_offset is None)
            # are left untouched. This only fires on this first
            # blank-to-set transition; later start date changes don't
            # re-trigger it, so manual due-date edits made afterward aren't
            # overwritten.
            template_events = HireEvent.query.filter(
                HireEvent.candidate_id == candidate.id,
                HireEvent.day_offset.isnot(None),
            ).all()
            if template_events:
                for te in template_events:
                    te.due_date = start_date + timedelta(days=te.day_offset)
                db.session.commit()
                flash(
                    f"Start date set — recalculated due dates for "
                    f"{len(template_events)} template-generated task(s).",
                    "info",
                )

        return redirect(url_for("candidates.detail", candidate_id=candidate.id))

    return render_template("candidates/form.html", candidate=candidate, form=None)


@candidates_bp.route("/<int:candidate_id>/delete", methods=["POST"])
@login_required
def delete_candidate(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    upload_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], str(candidate.id))
    db.session.delete(candidate)
    db.session.commit()

    if os.path.isdir(upload_dir):
        import shutil

        shutil.rmtree(upload_dir, ignore_errors=True)

    flash("Candidate deleted.", "info")
    return redirect(url_for("candidates.list_candidates"))


# --- Resumes ---------------------------------------------------------------

def _save_resumes(candidate, files):
    """Save each valid uploaded file as a Resume row for candidate.

    Skips empty file slots silently and flashes a warning for any file with
    a disallowed extension. Returns the number of files actually saved.
    Callers are responsible for checking whether any files were provided at
    all (required vs. optional differs by call site).
    """
    upload_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], str(candidate.id))
    os.makedirs(upload_dir, exist_ok=True)

    saved = 0
    for f in files:
        if not f or f.filename == "":
            continue
        if not _allowed_resume(f.filename):
            flash(f"'{f.filename}' is not an allowed file type (pdf/doc/docx).", "danger")
            continue

        original_filename = secure_filename(f.filename)
        stored_name = f"{uuid.uuid4().hex}_{original_filename}"
        stored_path = os.path.join(upload_dir, stored_name)
        f.save(stored_path)

        resume = Resume(
            candidate_id=candidate.id,
            original_filename=original_filename,
            stored_path=stored_path,
            uploaded_by=current_user.id,
        )
        db.session.add(resume)
        saved += 1

    if saved:
        db.session.commit()

    return saved


@candidates_bp.route("/<int:candidate_id>/resumes", methods=["POST"])
@login_required
def upload_resume(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    files = request.files.getlist("resume_file")

    if not files or all(f.filename == "" for f in files):
        flash("Please choose at least one file to upload.", "danger")
        return redirect(url_for("candidates.detail", candidate_id=candidate.id))

    saved = _save_resumes(candidate, files)
    if saved:
        flash(f"Uploaded {saved} resume file(s).", "success")

    return redirect(url_for("candidates.detail", candidate_id=candidate.id))


@candidates_bp.route("/<int:candidate_id>/resumes/<int:resume_id>/download")
@login_required
def download_resume(candidate_id, resume_id):
    resume = Resume.query.get_or_404(resume_id)
    if resume.candidate_id != candidate_id:
        abort(404)
    directory, filename = os.path.split(resume.stored_path)
    return send_from_directory(directory, filename, as_attachment=True, download_name=resume.original_filename)


@candidates_bp.route("/<int:candidate_id>/resumes/<int:resume_id>/delete", methods=["POST"])
@login_required
def delete_resume(candidate_id, resume_id):
    resume = Resume.query.get_or_404(resume_id)
    if resume.candidate_id != candidate_id:
        abort(404)

    if os.path.exists(resume.stored_path):
        try:
            os.remove(resume.stored_path)
        except OSError:
            pass

    db.session.delete(resume)
    db.session.commit()
    flash("Resume deleted.", "info")
    return redirect(url_for("candidates.detail", candidate_id=candidate_id))


# --- Notes -------------------------------------------------------------

@candidates_bp.route("/<int:candidate_id>/notes", methods=["POST"])
@login_required
def add_note(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    body = request.form.get("body", "").strip()

    if not body:
        flash("Note text cannot be empty.", "danger")
        return redirect(url_for("candidates.detail", candidate_id=candidate.id))

    note = Note(candidate_id=candidate.id, author_id=current_user.id, body=body)
    db.session.add(note)
    db.session.commit()
    flash("Note added.", "success")
    return redirect(url_for("candidates.detail", candidate_id=candidate.id))


@candidates_bp.route("/<int:candidate_id>/notes/<int:note_id>/delete", methods=["POST"])
@login_required
def delete_note(candidate_id, note_id):
    note = Note.query.get_or_404(note_id)
    if note.candidate_id != candidate_id:
        abort(404)

    if not current_user.is_admin and note.author_id != current_user.id:
        abort(403)

    db.session.delete(note)
    db.session.commit()
    flash("Note deleted.", "info")
    return redirect(url_for("candidates.detail", candidate_id=candidate_id))


# --- Timeline instantiation ------------------------------------------------

def _instantiate_timeline(candidate, template_name, timeline_type):
    template = TimelineTemplate.query.filter_by(name=template_name).first()
    if not template:
        return 0

    # Remove any previously generated events of this type so re-generating
    # doesn't create duplicates.
    HireEvent.query.filter_by(candidate_id=candidate.id, timeline_type=timeline_type).delete()

    base_date = candidate.start_date
    created = 0
    for te in template.events.order_by(TemplateEvent.sort_order).all():
        due_date = None
        if base_date is not None:
            due_date = base_date + timedelta(days=te.day_offset)
        event = HireEvent(
            candidate_id=candidate.id,
            title=te.title,
            description=te.description,
            due_date=due_date,
            assigned_to=None,
            status="pending",
            timeline_type=timeline_type,
            sort_order=te.sort_order,
            day_offset=te.day_offset,
        )
        db.session.add(event)
        created += 1

    return created


@candidates_bp.route("/<int:candidate_id>/generate-timelines", methods=["POST"])
@login_required
def generate_timelines(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.status != "hired":
        candidate.status = "hired"

    pre_created = _instantiate_timeline(candidate, "Pre-Hire", "pre_hire")
    post_created = _instantiate_timeline(candidate, "Post-Hire", "post_hire")
    db.session.commit()

    if not candidate.start_date:
        flash(
            "Timelines generated, but this candidate has no start date, so "
            "due dates could not be calculated. Set a start date and "
            "regenerate to populate due dates.",
            "warning",
        )
    else:
        flash(
            f"Generated {pre_created} pre-hire and {post_created} post-hire "
            "timeline events.",
            "success",
        )

    return redirect(url_for("candidates.detail", candidate_id=candidate.id))


# --- Hire events (per-candidate timeline items) -----------------------------

def _parse_recurrence(due_date):
    """Parse+validate the is_recurring/recurrence_interval/recurrence_unit
    fields from the current request's form. Returns
    (is_recurring, interval, unit, error) -- error is None when valid.
    Recurrence needs a due date: it's the anchor the first cycle (and
    every reset afterward, via app/recurring_tasks.py) counts from."""
    is_recurring = request.form.get("is_recurring") == "on"
    if not is_recurring:
        return False, None, None, None

    if due_date is None:
        return True, None, None, "A due date is required for a recurring task (it's the first occurrence)."

    unit = request.form.get("recurrence_unit", "").strip()
    if unit not in RECURRENCE_UNITS:
        return True, None, None, "Invalid recurrence unit."

    interval_raw = request.form.get("recurrence_interval", "").strip()
    try:
        interval = int(interval_raw)
        if interval < 1:
            raise ValueError
    except ValueError:
        return True, None, None, "Recurrence interval must be a whole number of at least 1."

    return True, interval, unit, None


@candidates_bp.route("/<int:candidate_id>/events", methods=["POST"])
@login_required
def add_event(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    due_date_raw = request.form.get("due_date", "").strip()
    timeline_type = request.form.get("timeline_type", "pre_hire")
    assigned_to = request.form.get("assigned_to", "").strip()

    error = None
    if not title:
        error = "Title is required."
    elif timeline_type not in TIMELINE_TYPES:
        error = "Invalid timeline type."

    due_date = None
    if due_date_raw:
        try:
            due_date = datetime.strptime(due_date_raw, "%Y-%m-%d").date()
        except ValueError:
            error = "Due date must be a valid date."

    assignee_id = None
    if assigned_to:
        try:
            assignee_id = int(assigned_to)
        except ValueError:
            assignee_id = None
            error = "Invalid assignee."
        else:
            if not User.query.get(assignee_id):
                error = "Invalid assignee."

    is_recurring, recurrence_interval, recurrence_unit, recurrence_error = _parse_recurrence(due_date)
    error = error or recurrence_error

    if error:
        flash(error, "danger")
        return redirect(url_for("candidates.detail", candidate_id=candidate.id))

    max_order = db.session.query(db.func.max(HireEvent.sort_order)).filter_by(
        candidate_id=candidate.id, timeline_type=timeline_type
    ).scalar() or 0

    event = HireEvent(
        candidate_id=candidate.id,
        title=title,
        description=description or None,
        due_date=due_date,
        assigned_to=assignee_id,
        status="pending",
        timeline_type=timeline_type,
        sort_order=max_order + 1,
        is_recurring=is_recurring,
        recurrence_interval=recurrence_interval,
        recurrence_unit=recurrence_unit,
    )
    db.session.add(event)
    db.session.commit()
    flash("Event added to timeline.", "success")
    return redirect(url_for("candidates.detail", candidate_id=candidate.id))


def _email_task_form_kwargs(candidate, task_type, due_date_raw, timeline_type, subject, body, previewed):
    return dict(
        candidate=candidate,
        email_task_types=EMAIL_TASK_TYPES,
        task_type=task_type,
        due_date=due_date_raw,
        timeline_type=timeline_type,
        subject=subject,
        body=body,
        to_display=email_task_recipient(task_type, candidate) or "(candidate has no email on file)",
        previewed=previewed,
    )


@candidates_bp.route("/<int:candidate_id>/events/email-task/new", methods=["GET", "POST"])
@login_required
def new_email_task(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)

    if request.method == "POST":
        step = request.form.get("step", "preview")
        task_type = request.form.get("task_type", EMAIL_TASK_TYPES[0])
        due_date_raw = request.form.get("due_date", "").strip()
        timeline_type = request.form.get("timeline_type", "pre_hire")
        label = EMAIL_TASK_TYPE_LABELS.get(task_type, task_type)

        error = None
        due_date = None
        if task_type not in EMAIL_TASK_TYPES:
            error = "Invalid email type."
        elif not due_date_raw:
            error = "Due date is required — this is the date the email will be sent."
        else:
            try:
                due_date = datetime.strptime(due_date_raw, "%Y-%m-%d").date()
            except ValueError:
                error = "Due date must be a valid date."

        if not error and timeline_type not in TIMELINE_TYPES:
            error = "Invalid timeline type."

        if not error and not email_task_recipient(task_type, candidate):
            error = f"This candidate has no email address on file, so a {label} email can't be created for them."

        if error:
            flash(error, "danger")
            return render_template(
                "candidates/email_task_form.html",
                **_email_task_form_kwargs(
                    candidate, task_type, due_date_raw, timeline_type,
                    request.form.get("subject"), request.form.get("body"), step == "create",
                ),
            )

        if step == "preview":
            existing = (
                HireEvent.query.filter_by(
                    candidate_id=candidate.id, task_type=task_type, status="pending"
                )
                .filter(HireEvent.email_sent_at.is_(None))
                .first()
            )
            if existing:
                flash(
                    f"This candidate already has a pending, unsent {label} email task. "
                    "Delete it first if you don't want to send two emails.",
                    "warning",
                )

            subject, body = render_email_task_template(task_type, candidate, current_user)
            return render_template(
                "candidates/email_task_form.html",
                **_email_task_form_kwargs(candidate, task_type, due_date_raw, timeline_type, subject, body, True),
            )

        # step == "create"
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "").strip()

        if not subject or not body:
            flash("Subject and body cannot be empty.", "danger")
            return render_template(
                "candidates/email_task_form.html",
                **_email_task_form_kwargs(candidate, task_type, due_date_raw, timeline_type, subject, body, True),
            )

        max_order = db.session.query(db.func.max(HireEvent.sort_order)).filter_by(
            candidate_id=candidate.id, timeline_type=timeline_type
        ).scalar() or 0

        event = HireEvent(
            candidate_id=candidate.id,
            title=email_task_title(task_type),
            task_type=task_type,
            email_subject=subject,
            email_body=body,
            due_date=due_date,
            assigned_to=None,
            status="pending",
            timeline_type=timeline_type,
            sort_order=max_order + 1,
            created_by=current_user.id,
        )
        db.session.add(event)
        db.session.commit()
        flash(f"{label} email task created.", "success")
        return redirect(url_for("candidates.detail", candidate_id=candidate.id))

    default_timeline_type = request.args.get("timeline_type", "pre_hire")
    if default_timeline_type not in TIMELINE_TYPES:
        default_timeline_type = "pre_hire"

    return render_template(
        "candidates/email_task_form.html",
        **_email_task_form_kwargs(
            candidate, EMAIL_TASK_TYPES[0], "", default_timeline_type, None, None, False
        ),
    )


@candidates_bp.route("/<int:candidate_id>/events/<int:event_id>/edit", methods=["POST"])
@login_required
def edit_event(candidate_id, event_id):
    event = HireEvent.query.get_or_404(event_id)
    if event.candidate_id != candidate_id:
        abort(404)

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    due_date_raw = request.form.get("due_date", "").strip()

    if not title:
        flash("Title is required.", "danger")
        return redirect(url_for("candidates.detail", candidate_id=candidate_id))

    due_date = None
    if due_date_raw:
        try:
            due_date = datetime.strptime(due_date_raw, "%Y-%m-%d").date()
        except ValueError:
            flash("Due date must be a valid date.", "danger")
            return redirect(url_for("candidates.detail", candidate_id=candidate_id))

    is_recurring, recurrence_interval, recurrence_unit, recurrence_error = _parse_recurrence(due_date)
    if recurrence_error:
        flash(recurrence_error, "danger")
        return redirect(url_for("candidates.detail", candidate_id=candidate_id))

    event.title = title
    event.description = description or None
    event.due_date = due_date
    event.is_recurring = is_recurring
    event.recurrence_interval = recurrence_interval
    event.recurrence_unit = recurrence_unit
    db.session.commit()
    flash("Event updated.", "success")
    return redirect(url_for("candidates.detail", candidate_id=candidate_id))


@candidates_bp.route("/<int:candidate_id>/events/<int:event_id>/delete", methods=["POST"])
@login_required
def delete_event(candidate_id, event_id):
    event = HireEvent.query.get_or_404(event_id)
    if event.candidate_id != candidate_id:
        abort(404)
    db.session.delete(event)
    db.session.commit()
    flash("Event removed.", "info")
    return redirect(url_for("candidates.detail", candidate_id=candidate_id))


@candidates_bp.route("/<int:candidate_id>/events/<int:event_id>/assign", methods=["POST"])
@login_required
def assign_event(candidate_id, event_id):
    event = HireEvent.query.get_or_404(event_id)
    if event.candidate_id != candidate_id:
        abort(404)

    if event.task_type != TASK_TYPE_MANUAL:
        flash("This task's assignee cannot be changed.", "danger")
        return redirect(url_for("candidates.detail", candidate_id=candidate_id))

    assigned_to = request.form.get("assigned_to", "").strip()
    if assigned_to:
        try:
            user = User.query.get(int(assigned_to))
        except ValueError:
            user = None
        if not user:
            flash("Invalid assignee.", "danger")
            return redirect(url_for("candidates.detail", candidate_id=candidate_id))
        event.assigned_to = user.id
        flash(f"Assigned '{event.title}' to {user.name}.", "success")
    else:
        event.assigned_to = None
        flash(f"Unassigned '{event.title}'.", "info")

    db.session.commit()
    return redirect(url_for("candidates.detail", candidate_id=candidate_id))


@candidates_bp.route("/<int:candidate_id>/events/<int:event_id>/toggle", methods=["POST"])
@login_required
def toggle_event(candidate_id, event_id):
    event = HireEvent.query.get_or_404(event_id)
    if event.candidate_id != candidate_id:
        abort(404)

    if event.task_type != TASK_TYPE_MANUAL:
        flash("This task is completed automatically when its email is sent.", "danger")
        return redirect(url_for("candidates.detail", candidate_id=candidate_id))

    event.status = "done" if event.status == "pending" else "pending"
    db.session.commit()
    return redirect(url_for("candidates.detail", candidate_id=candidate_id))
