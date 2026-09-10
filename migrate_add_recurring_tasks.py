"""One-off migration: adds the recurrence columns to hire_events
(is_recurring, recurrence_interval, recurrence_unit) used by recurring
manual tasks (see app/recurring_tasks.py).

    python migrate_add_recurring_tasks.py

Idempotent -- safe to re-run. Uses create_app() + SQLAlchemy (config.py
is stable now). Manual, one-off script, not run from create_app() itself:
onboarding.service runs multiple gunicorn workers, and DDL shouldn't run
concurrently from several worker boots.
"""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db

NEW_COLUMNS = {
    "is_recurring": "BOOLEAN NOT NULL DEFAULT 0",
    "recurrence_interval": "INTEGER",
    "recurrence_unit": "VARCHAR(10)",
}


def main():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        existing_columns = {col["name"] for col in inspector.get_columns("hire_events")}

        added = []
        with db.engine.begin() as conn:
            for name, ddl in NEW_COLUMNS.items():
                if name in existing_columns:
                    continue
                conn.execute(text(f"ALTER TABLE hire_events ADD COLUMN {name} {ddl}"))
                added.append(name)

        if added:
            print(f"Added columns to hire_events: {', '.join(added)}")
        else:
            print("hire_events already has all required columns. Nothing to do.")


if __name__ == "__main__":
    main()
