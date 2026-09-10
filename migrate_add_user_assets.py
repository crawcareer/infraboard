"""One-off migration: creates the assets and user_assets tables (used by
Admin > User Asset Inventory and the Team page's per-user checkboxes) if
they don't already exist.

    python migrate_add_user_assets.py

Same idempotent, create_app() + SQLAlchemy pattern as the other
migrate_add_*_table.py scripts. Not run from create_app() itself:
onboarding.service runs multiple gunicorn workers, and DDL shouldn't run
concurrently from several worker boots.
"""

from app import create_app
from app.extensions import db
from app.models import Asset, user_assets


def main():
    app = create_app()
    with app.app_context():
        Asset.__table__.create(bind=db.engine, checkfirst=True)
        user_assets.create(bind=db.engine, checkfirst=True)
    print("assets and user_assets tables ensured.")


if __name__ == "__main__":
    main()
