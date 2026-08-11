from datetime import date

from flask import Blueprint, render_template
from flask_login import login_required, current_user

from app.models import Candidate, HireEvent, CANDIDATE_STATUSES

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def dashboard():
    candidates_by_status = {}
    for status in CANDIDATE_STATUSES:
        candidates_by_status[status] = (
            Candidate.query.filter_by(status=status).order_by(Candidate.name).all()
        )

    my_tasks = (
        HireEvent.query.filter_by(assigned_to=current_user.id, status="pending")
        .order_by(HireEvent.due_date.is_(None), HireEvent.due_date)
        .all()
    )

    today = date.today()

    return render_template(
        "dashboard.html",
        candidates_by_status=candidates_by_status,
        my_tasks=my_tasks,
        today=today,
    )
