"""Runs the Active Directory / LDAP sync if enough time has passed since
the last one, per the admin-configured sync interval (Admin > Active
Directory Integration).

    python sync_ldap_employees.py

Intended to run frequently via deploy/onboarding-ldap-sync.timer (e.g.
every 5 minutes) as a heartbeat -- this script itself decides whether a
sync is actually due, so the timer doesn't need editing every time the
interval setting changes.
"""

from datetime import datetime, timedelta

from app import create_app
from app.extensions import db
from app.ldap_sync import run_sync
from app.models import LdapSettings


def main():
    app = create_app()
    with app.app_context():
        settings = LdapSettings.query.first()
        if not settings or not settings.host:
            print("LDAP is not configured. Nothing to do.")
            return

        if settings.last_sync_at:
            due_at = settings.last_sync_at + timedelta(minutes=settings.sync_interval_minutes)
            if datetime.utcnow() < due_at:
                print(f"Not due until {due_at} UTC. Skipping.")
                return

        try:
            result = run_sync(settings)
        except Exception as exc:
            settings.last_sync_at = datetime.utcnow()
            settings.last_sync_status = "error"
            settings.last_sync_message = str(exc)
            db.session.commit()
            print(f"Sync failed: {exc}")
            return

        settings.last_sync_at = datetime.utcnow()
        settings.last_sync_status = "ok"
        settings.last_sync_message = "; ".join(result.errors) if result.errors else None
        settings.last_sync_created = result.created
        settings.last_sync_updated = result.updated
        settings.last_sync_deactivated = result.deactivated
        db.session.commit()

        print(
            f"Sync complete: {result.created} created, {result.updated} updated, "
            f"{result.deactivated} deactivated, {len(result.errors)} error(s)."
        )
        for error in result.errors:
            print(f"  - {error}")


if __name__ == "__main__":
    main()
