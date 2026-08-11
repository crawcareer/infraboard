import secrets

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    abort,
)
from flask_login import login_user, logout_user, login_required, current_user

from app.extensions import db
from app.models import User, ROLES, ROLE_ADMIN

auth_bp = Blueprint("auth", __name__)


def admin_required(view):
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager_redirect()
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def login_manager_redirect():
    return redirect(url_for("auth.login", next=request.path))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if user and user.active and user.check_password(password):
            login_user(user)
            flash(f"Welcome back, {user.name}.", "success")
            next_url = request.args.get("next")
            if next_url and next_url.startswith("/"):
                return redirect(next_url)
            return redirect(url_for("main.dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


# --- Team management (admin only) ---------------------------------------

@auth_bp.route("/team")
@login_required
@admin_required
def team_list():
    users = User.query.order_by(User.name).all()
    return render_template("team/list.html", users=users)


@auth_bp.route("/team/new", methods=["GET", "POST"])
@login_required
@admin_required
def team_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        role = request.form.get("role", "member")
        password = request.form.get("password", "")

        error = None
        if not name or not email or not password:
            error = "Name, email, and password are required."
        elif role not in ROLES:
            error = "Invalid role."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif User.query.filter_by(email=email).first():
            error = "A team member with that email already exists."

        if error:
            flash(error, "danger")
            return render_template("team/form.html", user=None, form=request.form)

        user = User(name=name, email=email, role=role, active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f"Team member {name} created.", "success")
        return redirect(url_for("auth.team_list"))

    return render_template("team/form.html", user=None, form={})


@auth_bp.route("/team/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def team_edit(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        role = request.form.get("role", "member")
        active = request.form.get("active") == "on"
        new_password = request.form.get("password", "").strip()

        error = None
        if not name or not email:
            error = "Name and email are required."
        elif role not in ROLES:
            error = "Invalid role."
        else:
            existing = User.query.filter_by(email=email).first()
            if existing and existing.id != user.id:
                error = "Another team member already uses that email."

        if user.id == current_user.id and not active:
            error = "You cannot deactivate your own account."
        if user.id == current_user.id and role != ROLE_ADMIN:
            error = "You cannot remove your own admin role."

        if new_password and len(new_password) < 8:
            error = "New password must be at least 8 characters."

        if error:
            flash(error, "danger")
            return render_template("team/form.html", user=user, form=request.form)

        user.name = name
        user.email = email
        user.role = role
        user.active = active
        if new_password:
            user.set_password(new_password)
        db.session.commit()
        flash(f"Team member {name} updated.", "success")
        return redirect(url_for("auth.team_list"))

    return render_template("team/form.html", user=user, form=None)


@auth_bp.route("/team/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def team_delete(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("auth.team_list"))

    # Preserve historical data integrity: unassign this user's events and
    # detach authorship rather than cascading deletes across candidates.
    from app.models import HireEvent, Note, Resume

    HireEvent.query.filter_by(assigned_to=user.id).update({"assigned_to": None})
    Note.query.filter_by(author_id=user.id).update({"author_id": None})
    Resume.query.filter_by(uploaded_by=user.id).update({"uploaded_by": None})

    db.session.delete(user)
    db.session.commit()
    flash("Team member removed.", "info")
    return redirect(url_for("auth.team_list"))


@auth_bp.route("/team/<int:user_id>/reset-password", methods=["POST"])
@login_required
@admin_required
def team_reset_password(user_id):
    user = User.query.get_or_404(user_id)
    new_password = secrets.token_urlsafe(9)
    user.set_password(new_password)
    db.session.commit()
    flash(
        f"Password for {user.name} has been reset to: {new_password} "
        "(share this securely — it will not be shown again).",
        "warning",
    )
    return redirect(url_for("auth.team_list"))
