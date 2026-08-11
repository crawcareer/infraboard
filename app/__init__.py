import os
import secrets

from flask import Flask, session, request, abort, render_template
from flask_login import current_user

from config import Config
from app.extensions import db, login_manager


def create_app(config_class=Config):
    # Pin the instance path explicitly to <project root>/instance. Flask's
    # automatic instance_path detection resolves relative to the "app"
    # package's own directory (giving .../app/instance) rather than the
    # project root, which doesn't match where config.py points the SQLite
    # database (.../instance/onboarding.db). Passing instance_path here
    # keeps both in sync regardless of how the app is packaged/deployed.
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    instance_path = os.path.join(project_root, "instance")

    app = Flask(__name__, instance_relative_config=True, instance_path=instance_path)
    app.config.from_object(config_class)

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # --- Blueprints -----------------------------------------------------
    from app.auth import auth_bp
    from app.candidates import candidates_bp
    from app.templates_admin import templates_admin_bp
    from app.main import main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(candidates_bp)
    app.register_blueprint(templates_admin_bp)
    app.register_blueprint(main_bp)

    # --- Lightweight CSRF protection ------------------------------------
    # The app intentionally avoids extra heavy dependencies (Flask-WTF)
    # while still protecting all state-changing (POST) requests with a
    # per-session token that every form template includes.
    @app.before_request
    def _csrf_protect():
        if request.method == "POST":
            token = session.get("_csrf_token")
            form_token = request.form.get("csrf_token")
            if not token or not form_token or not secrets.compare_digest(token, form_token):
                abort(400, description="Invalid or missing CSRF token. Please retry.")

    @app.context_processor
    def _inject_csrf_token():
        if "_csrf_token" not in session:
            session["_csrf_token"] = secrets.token_hex(16)
        return {"csrf_token": session["_csrf_token"]}

    @app.context_processor
    def _inject_globals():
        from app.models import CANDIDATE_STATUSES, ROLES, TIMELINE_TYPES

        return {
            "candidate_statuses": CANDIDATE_STATUSES,
            "roles": ROLES,
            "timeline_types": TIMELINE_TYPES,
            "current_user": current_user,
        }

    @app.template_filter("dtfmt")
    def _dtfmt(value, fmt="%Y-%m-%d"):
        if value is None:
            return ""
        return value.strftime(fmt)

    @app.errorhandler(403)
    def _forbidden(e):
        return render_template("errors/error.html", code=403, message="Forbidden"), 403

    @app.errorhandler(404)
    def _not_found(e):
        return render_template("errors/error.html", code=404, message="Not found"), 404

    @app.errorhandler(400)
    def _bad_request(e):
        return render_template("errors/error.html", code=400, message=str(e.description or "Bad request")), 400

    return app
