"""Creates a fresh local instance/onboarding.db with the full schema and a
test admin login, for local development/testing only.

    python dev_seed_db.py

Uses db.create_all(), which only creates tables that don't already exist —
safe to run against a database that already has some or all tables (won't
drop or touch existing data). Skips creating the test admin if one with the
same email already exists.
"""

from app import create_app
from app.extensions import db
from app.models import User, ROLE_ADMIN

TEST_ADMIN_EMAIL = "admin@example.com"
TEST_ADMIN_PASSWORD = "adminpass123"


def main():
    app = create_app()
    with app.app_context():
        db.create_all()

        if User.query.filter_by(email=TEST_ADMIN_EMAIL).first():
            print(f"Test admin {TEST_ADMIN_EMAIL} already exists. Schema ensured, nothing else to do.")
            return

        admin = User(name="Test Admin", email=TEST_ADMIN_EMAIL, role=ROLE_ADMIN, active=True)
        admin.set_password(TEST_ADMIN_PASSWORD)
        db.session.add(admin)
        db.session.commit()

        print("Created a fresh local database with the full schema.")
        print(f"Test admin login: {TEST_ADMIN_EMAIL} / {TEST_ADMIN_PASSWORD}")


if __name__ == "__main__":
    main()
