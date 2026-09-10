"""One-off migration: adds the task_type column to email_templates, so
each of the automated email task types (Infradapt Onboarding, Rejection,
Interview Request - Phone, Interview Request - In Person, Offer) gets its
own row/template instead of the one shared singleton it used to be.

    python migrate_add_email_template_types.py

Idempotent. If email_templates doesn't exist at all yet, creates it fresh
from the current model (which already includes task_type) instead of
altering it. If a row already exists without a task_type -- the old
singleton, from before this migration -- it's backfilled to
'infradapt_onboarding_email', since that was the only template that
existed before this feature.

Note: SQLite's ALTER TABLE ADD COLUMN can't add a UNIQUE constraint, so a
database migrated this way won't have one at the DB level the way a fresh
install's CREATE TABLE would -- uniqueness per type is enforced at the
application layer instead (see app/admin.py's get-or-create-by-type
logic), which is sufficient here since email_templates is only ever
written to through that one code path.
"""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db
from app.models import EmailTemplate, TASK_TYPE_INFRADAPT_ONBOARDING_EMAIL


def main():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)

        if not inspector.has_table("email_templates"):
            EmailTemplate.__table__.create(bind=db.engine, checkfirst=True)
            print("email_templates table created fresh (already includes task_type).")
            return

        existing_columns = {col["name"] for col in inspector.get_columns("email_templates")}
        if "task_type" in existing_columns:
            print("email_templates.task_type already exists. Nothing to do.")
            return

        with db.engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE email_templates ADD COLUMN task_type VARCHAR(40) "
                    f"NOT NULL DEFAULT '{TASK_TYPE_INFRADAPT_ONBOARDING_EMAIL}'"
                )
            )
        print("Added email_templates.task_type (existing row(s) backfilled as Infradapt Onboarding).")


if __name__ == "__main__":
    main()
