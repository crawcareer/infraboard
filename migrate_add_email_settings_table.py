"""One-off migration: creates the email_settings table (used by
Admin > Email Settings) if it doesn't already exist.

    python migrate_add_email_settings_table.py

Unlike the earlier migrate_add_*_columns.py scripts — which used raw
sqlite3 because config.py/run.py didn't exist on disk at the time — this
one goes through create_app() + SQLAlchemy, since config.py is back and
stable, and letting SQLAlchemy generate the CREATE TABLE from the model is
more reliable than hand-written DDL for a brand-new table.

Still a manual, one-off script — not wired into create_app() itself.
onboarding.service runs multiple gunicorn workers, and DDL should not run
concurrently from several worker boots.

Requires the 'cryptography' package to be installed (used by
app/crypto.py, imported transitively via app.emailing): pip install
cryptography
"""

from app import create_app
from app.extensions import db
from app.models import EmailSettings


def main():
    app = create_app()
    with app.app_context():
        EmailSettings.__table__.create(bind=db.engine, checkfirst=True)
    print("email_settings table ensured.")


if __name__ == "__main__":
    main()
