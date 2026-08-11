from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required

from app.extensions import db
from app.models import TimelineTemplate, TemplateEvent, ROLES
from app.auth import admin_required

templates_admin_bp = Blueprint(
    "templates_admin", __name__, url_prefix="/timeline-templates"
)


@templates_admin_bp.route("/")
@login_required
@admin_required
def list_templates():
    templates = TimelineTemplate.query.order_by(TimelineTemplate.name).all()
    return render_template("templates_admin/list.html", templates=templates)


@templates_admin_bp.route("/new", methods=["GET", "POST"])
@login_required
@admin_required
def new_template():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()

        if not name:
            flash("Template name is required.", "danger")
            return render_template("templates_admin/form.html", template=None)

        if TimelineTemplate.query.filter_by(name=name).first():
            flash("A template with that name already exists.", "danger")
            return render_template("templates_admin/form.html", template=None)

        template = TimelineTemplate(name=name, description=description or None)
        db.session.add(template)
        db.session.commit()
        flash(f"Template '{name}' created.", "success")
        return redirect(url_for("templates_admin.detail", template_id=template.id))

    return render_template("templates_admin/form.html", template=None)


@templates_admin_bp.route("/<int:template_id>")
@login_required
@admin_required
def detail(template_id):
    template = TimelineTemplate.query.get_or_404(template_id)
    events = template.events.order_by(TemplateEvent.sort_order).all()
    return render_template("templates_admin/detail.html", template=template, events=events)


@templates_admin_bp.route("/<int:template_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_template(template_id):
    template = TimelineTemplate.query.get_or_404(template_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()

        if not name:
            flash("Template name is required.", "danger")
            return render_template("templates_admin/form.html", template=template)

        existing = TimelineTemplate.query.filter_by(name=name).first()
        if existing and existing.id != template.id:
            flash("A template with that name already exists.", "danger")
            return render_template("templates_admin/form.html", template=template)

        template.name = name
        template.description = description or None
        db.session.commit()
        flash("Template updated.", "success")
        return redirect(url_for("templates_admin.detail", template_id=template.id))

    return render_template("templates_admin/form.html", template=template)


@templates_admin_bp.route("/<int:template_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_template(template_id):
    template = TimelineTemplate.query.get_or_404(template_id)
    db.session.delete(template)
    db.session.commit()
    flash("Template deleted.", "info")
    return redirect(url_for("templates_admin.list_templates"))


# --- Template events ---------------------------------------------------

@templates_admin_bp.route("/<int:template_id>/events/new", methods=["POST"])
@login_required
@admin_required
def add_event(template_id):
    template = TimelineTemplate.query.get_or_404(template_id)

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    day_offset_raw = request.form.get("day_offset", "0").strip()
    default_assignee_role = request.form.get("default_assignee_role", "").strip()

    error = None
    if not title:
        error = "Title is required."
    try:
        day_offset = int(day_offset_raw)
    except ValueError:
        error = "Day offset must be an integer."
        day_offset = 0

    if default_assignee_role and default_assignee_role not in ROLES:
        error = "Invalid default role."

    if error:
        flash(error, "danger")
        return redirect(url_for("templates_admin.detail", template_id=template.id))

    max_order = db.session.query(db.func.max(TemplateEvent.sort_order)).filter_by(
        template_id=template.id
    ).scalar()
    next_order = (max_order + 1) if max_order is not None else 0

    event = TemplateEvent(
        template_id=template.id,
        title=title,
        description=description or None,
        day_offset=day_offset,
        default_assignee_role=default_assignee_role or None,
        sort_order=next_order,
    )
    db.session.add(event)
    db.session.commit()
    flash("Event added.", "success")
    return redirect(url_for("templates_admin.detail", template_id=template.id))


@templates_admin_bp.route(
    "/<int:template_id>/events/<int:event_id>/edit", methods=["POST"]
)
@login_required
@admin_required
def edit_event(template_id, event_id):
    event = TemplateEvent.query.get_or_404(event_id)
    if event.template_id != template_id:
        abort(404)

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    day_offset_raw = request.form.get("day_offset", "0").strip()
    default_assignee_role = request.form.get("default_assignee_role", "").strip()

    error = None
    if not title:
        error = "Title is required."
    try:
        day_offset = int(day_offset_raw)
    except ValueError:
        error = "Day offset must be an integer."
        day_offset = event.day_offset

    if default_assignee_role and default_assignee_role not in ROLES:
        error = "Invalid default role."

    if error:
        flash(error, "danger")
        return redirect(url_for("templates_admin.detail", template_id=template_id))

    event.title = title
    event.description = description or None
    event.day_offset = day_offset
    event.default_assignee_role = default_assignee_role or None
    db.session.commit()
    flash("Event updated.", "success")
    return redirect(url_for("templates_admin.detail", template_id=template_id))


@templates_admin_bp.route(
    "/<int:template_id>/events/<int:event_id>/delete", methods=["POST"]
)
@login_required
@admin_required
def delete_event(template_id, event_id):
    event = TemplateEvent.query.get_or_404(event_id)
    if event.template_id != template_id:
        abort(404)
    db.session.delete(event)
    db.session.commit()
    flash("Event removed.", "info")
    return redirect(url_for("templates_admin.detail", template_id=template_id))


def _swap_order(template_id, event_id, direction):
    event = TemplateEvent.query.get_or_404(event_id)
    if event.template_id != template_id:
        abort(404)

    events = (
        TemplateEvent.query.filter_by(template_id=template_id)
        .order_by(TemplateEvent.sort_order)
        .all()
    )
    idx = next((i for i, e in enumerate(events) if e.id == event.id), None)
    if idx is None:
        return

    swap_idx = idx - 1 if direction == "up" else idx + 1
    if 0 <= swap_idx < len(events):
        other = events[swap_idx]
        event.sort_order, other.sort_order = other.sort_order, event.sort_order
        db.session.commit()


@templates_admin_bp.route(
    "/<int:template_id>/events/<int:event_id>/move-up", methods=["POST"]
)
@login_required
@admin_required
def move_event_up(template_id, event_id):
    _swap_order(template_id, event_id, "up")
    return redirect(url_for("templates_admin.detail", template_id=template_id))


@templates_admin_bp.route(
    "/<int:template_id>/events/<int:event_id>/move-down", methods=["POST"]
)
@login_required
@admin_required
def move_event_down(template_id, event_id):
    _swap_order(template_id, event_id, "down")
    return redirect(url_for("templates_admin.detail", template_id=template_id))
