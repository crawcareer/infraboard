"""One-off, idempotent migration: adds the HireEvent.day_offset column used
to backfill due dates on template-generated tasks when a candidate's start
date is set after the fact.

This project has no migration framework (no Alembic/Flask-Migrate), so this
is a plain script instead of app-startup auto-migration — run it by hand,
once, before restarting the app:

    python migrate_add_day_offset_column.py

Do NOT wire this into create_app()/app startup: onboarding.service runs
gunicorn with multiple workers, and concurrent ALTER TABLE calls against the
same SQLite file from several worker processes booting at once will race.

Reads the database path from SQLALCHEMY_DATABASE_URI (same env var
config.py uses), falling back to the project's default
instance/onboarding.db, matching the default documented in .env.
"""

import os
import sqlite3
from urllib.parse import urlparse

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(PROJECT_ROOT, "instance", "onboarding.db")

NEW_COLUMNS = {
    "day_offset": "INTEGER",
}


def _resolve_sqlite_path():
    uri = os.environ.get("SQLALCHEMY_DATABASE_URI", "").strip()
    if not uri:
        return DEFAULT_DB_PATH

    parsed = urlparse(uri)
    if parsed.scheme != "sqlite":
        raise SystemExit(
            f"SQLALCHEMY_DATABASE_URI is '{parsed.scheme}', not sqlite. "
            "This script only knows how to migrate a SQLite file directly; "
            "adapt it (or run the equivalent ALTER TABLE statements by hand) "
            "for other databases."
        )

    path = parsed.path
    if uri.startswith("sqlite:////"):
        return path
    return os.path.join(PROJECT_ROOT, path.lstrip("/"))


def main():
    db_path = _resolve_sqlite_path()
    if not os.path.exists(db_path):
        raise SystemExit(f"Database file not found: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute("PRAGMA table_info(hire_events)")
        existing_columns = {row[1] for row in cur.fetchall()}

        added = []
        for name, ddl in NEW_COLUMNS.items():
            if name in existing_columns:
                continue
            conn.execute(f"ALTER TABLE hire_events ADD COLUMN {name} {ddl}")
            added.append(name)

        conn.commit()
    finally:
        conn.close()

    if added:
        print(f"Added columns to hire_events: {', '.join(added)}")
    else:
        print("hire_events already has all required columns. Nothing to do.")


if __name__ == "__main__":
    main()
