"""One-time setup for a brand-new deployment: creates the full database
schema and the first admin account.

    python init_production_db.py

Safe to re-run: db.create_all() only creates tables that don't already
exist, and this skips creating an admin if any user already exists.

For local development/testing, use dev_seed_db.py instead -- it seeds a
fixed, publicly-known test password, which is fine for a throwaway local
database but wrong for a real server.
"""

import getpass
import sys

from app import create_app
from app.extensions import db
from app.models import ROLE_ADMIN, User


def main():
    app = create_app()
    with app.app_context():
        db.create_all()
        print("Database schema created (or already up to date).")

        if User.query.first() is not None:
            print("A user account already exists -- skipping admin creation.")
            return

        print("\nNo accounts exist yet. Let's create the first admin login.")
        name = input("Admin name: ").strip()
        email = input("Admin email: ").strip().lower()

        password = getpass.getpass("Admin password (min 8 characters): ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords didn't match. Run this script again to try again.")
            sys.exit(1)
        if len(password) < 8:
            print("Password must be at least 8 characters. Run this script again to try again.")
            sys.exit(1)

        admin = User(name=name, email=email, role=ROLE_ADMIN, active=True)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()

        print(f"\nCreated admin account for {email}. You can log in now.")


if __name__ == "__main__":
    main()
