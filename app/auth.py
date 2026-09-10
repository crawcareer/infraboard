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
from app.models import Asset, User, ROLES, ROLE_ADMIN, ROLE_EMPLOYEE

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

        authenticated = False
        if user and user.active:
            if user.is_ldap_synced:
                # Synced accounts have no usable local password (see
                # User.password_hash / app/ldap_sync.py) -- Active
                # Directory is the live authority on every login. Any
                # LDAP error (unreachable, bad creds, misconfigured
                # settings) falls through to authenticated=False, i.e.
                # fails closed rather than granting access.
                from app.ldap_sync import check_login_bind
                from app.models import LdapSettings

                ldap_settings = LdapSettings.query.first()
                authenticated = check_login_bind(ldap_settings, user.ldap_dn, password)
            else:
                authenticated = user.check_password(password)

        if authenticated:
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


# --- Team management -----------------------------------------------------
# Viewable by any signed-in user (Employees included, so they can toggle
# asset checkboxes). Adding, removing, resetting a password, and changing
# anything about a user other than their assets stays admin-only -- see
# team_edit's branch on current_user.is_admin below.

@auth_bp.route("/team")
@login_required
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
        role = request.form.get("role", ROLE_EMPLOYEE)
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

        # Every field here was explicitly chosen by an admin, not defaulted
        # or synced -- lock them all from the start so a later LDAP sync
        # that happens to match this account's email won't silently
        # change anything about it.
        user = User(
            name=name,
            email=email,
            role=role,
            active=True,
            name_locked=True,
            email_locked=True,
            role_locked=True,
            active_locked=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f"Team member {name} created.", "success")
        return redirect(url_for("auth.team_list"))

    return render_template("team/form.html", user=None, form={})


def _apply_asset_selection(user, all_assets):
    selected_ids = {int(v) for v in request.form.getlist("asset_ids") if v.isdigit()}
    user.assets = [a for a in all_assets if a.id in selected_ids]


@auth_bp.route("/team/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
def team_edit(user_id):
    user = User.query.get_or_404(user_id)
    all_assets = Asset.query.order_by(Asset.name).all()

    if request.method == "POST":
        if not current_user.is_admin:
            # Employees only ever reach this branch. Every other field
            # (name/email/role/active/password) is simply never read from
            # the request here, no matter what a crafted POST might
            # include -- there's nothing below that could promote or
            # demote anyone, only the asset list gets touched.
            _apply_asset_selection(user, all_assets)
            db.session.commit()
            flash(f"Updated assets for {user.name}.", "success")
            return redirect(url_for("auth.team_list"))

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        role = request.form.get("role", ROLE_EMPLOYEE)
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
            return render_template("team/form.html", user=user, form=request.form, assets=all_assets)

        # An LDAP sync will skip any field marked locked here -- lock
        # exactly the fields actually being changed by this edit, not the
        # whole account, so sync can keep managing whatever wasn't
        # touched by hand.
        if name != user.name:
            user.name_locked = True
        if email != user.email:
            user.email_locked = True
        if role != user.role:
            user.role_locked = True
        if active != user.active:
            user.active_locked = True

        user.name = name
        user.email = email
        user.role = role
        user.active = active
        if new_password:
            user.set_password(new_password)
        _apply_asset_selection(user, all_assets)
        db.session.commit()
        flash(f"Team member {name} updated.", "success")
        return redirect(url_for("auth.team_list"))

    return render_template("team/form.html", user=user, form=None, assets=all_assets)


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
    HireEvent.query.filter_by(created_by=user.id).update({"created_by": None})
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
