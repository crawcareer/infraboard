"""One-off migration for Active Directory / LDAP sync support:

  - Adds the LDAP-sync columns to users (ldap_dn, ldap_username,
    is_ldap_synced, name_locked, email_locked, role_locked, active_locked).
  - Migrates any existing role='member' rows to role='employee' (the
    member role was retired in favor of employee).
  - Creates the ldap_settings table if it doesn't exist.

    python migrate_add_ldap_support.py

Idempotent -- safe to re-run. Uses create_app() + SQLAlchemy (config.py
is stable now; see the git history of the earlier migrate_add_*.py
scripts for why the very first ones used raw sqlite3 instead). Still a
manual, one-off script, not run from create_app() itself: onboarding.service
runs multiple gunicorn workers, and DDL shouldn't run concurrently from
several worker boots.
"""

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db
from app.models import LdapSettings

NEW_USER_COLUMNS = {
    "ldap_dn": "VARCHAR(500)",
    "ldap_username": "VARCHAR(255)",
    "is_ldap_synced": "BOOLEAN NOT NULL DEFAULT 0",
    "name_locked": "BOOLEAN NOT NULL DEFAULT 0",
    "email_locked": "BOOLEAN NOT NULL DEFAULT 0",
    "role_locked": "BOOLEAN NOT NULL DEFAULT 0",
    "active_locked": "BOOLEAN NOT NULL DEFAULT 0",
}


def main():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        existing_columns = {col["name"] for col in inspector.get_columns("users")}

        added = []
        with db.engine.begin() as conn:
            for name, ddl in NEW_USER_COLUMNS.items():
                if name in existing_columns:
                    continue
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))
                added.append(name)

            migrated = conn.execute(
                text("UPDATE users SET role = 'employee' WHERE role = 'member'")
            ).rowcount

        LdapSettings.__table__.create(bind=db.engine, checkfirst=True)

        if added:
            print(f"Added columns to users: {', '.join(added)}")
        else:
            print("users table already has all required columns.")
        print(f"Migrated {migrated} existing 'member' role user(s) to 'employee'.")
        print("ldap_settings table ensured.")


if __name__ == "__main__":
    main()
