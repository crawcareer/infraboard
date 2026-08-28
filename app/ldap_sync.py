"""Active Directory / LDAP sync engine.

Shared by Admin > Active Directory Integration's Test connection / Sync
now buttons, the standalone sync_ldap_employees.py script, and the login
route's LDAP bind check for synced accounts.

ldap3 is imported lazily inside functions, never at module level -- same
reasoning as app/crypto.py and the cryptography package: this module is
imported (transitively) by create_app(), so an eager top-level import
would mean the *entire app* fails to boot if ldap3 isn't installed yet,
instead of just LDAP features being unavailable until it is.

Attribute mapping is fixed to standard Active Directory conventions
rather than admin-configurable, to keep the settings form manageable.
"""

import secrets

from werkzeug.security import generate_password_hash

from app.crypto import decrypt_secret
from app.extensions import db

ATTR_USERNAME = "sAMAccountName"
ATTR_EMAIL = "mail"
ATTR_NAME = "displayName"
ATTR_UAC = "userAccountControl"

UAC_ACCOUNTDISABLE = 0x2


class LdapConfigError(Exception):
    """Raised when LdapSettings isn't configured enough to connect."""


def _require_config(settings):
    if not settings or not settings.host or not settings.search_base:
        raise LdapConfigError(
            "LDAP is not configured. Set it up in Admin > Active Directory Integration."
        )


def _connect(settings, user_dn=None, password=None):
    """Open an ldap3 Connection: bound as the configured service account
    when user_dn is None, or as a specific user (for login bind checks)
    when given."""
    import ldap3

    port = settings.port or (636 if settings.use_ssl else 389)
    server = ldap3.Server(settings.host, port=port, use_ssl=settings.use_ssl, get_info=ldap3.NONE)

    if user_dn is not None:
        bind_dn, bind_password = user_dn, password
    else:
        bind_dn = settings.bind_dn
        bind_password = decrypt_secret(settings.bind_password_encrypted)

    return ldap3.Connection(
        server, user=bind_dn, password=bind_password, auto_bind=True, raise_exceptions=True
    )


def test_connection(settings):
    """Attempt a bind + a scoped search. Returns (ok, message); never
    raises -- callers just display the message."""
    try:
        _require_config(settings)
        conn = _connect(settings)
        try:
            conn.search(
                settings.search_base,
                settings.user_filter or "(objectClass=*)",
                search_scope="SUBTREE",
                attributes=[ATTR_USERNAME],
                size_limit=1,
            )
        finally:
            conn.unbind()
        return True, "Connected and search succeeded."
    except LdapConfigError as exc:
        return False, str(exc)
    except Exception as exc:  # ldap3's own exception hierarchy
        return False, f"Connection failed: {exc}"


def check_login_bind(settings, ldap_dn, password):
    """Return True if binding as ldap_dn with password succeeds. Any
    error (network, bad creds, misconfiguration) returns False -- fail
    closed, since this sits directly on the login path."""
    try:
        _require_config(settings)
        if not ldap_dn or not password:
            return False
        conn = _connect(settings, user_dn=ldap_dn, password=password)
        conn.unbind()
        return True
    except Exception:
        return False


class SyncResult:
    def __init__(self):
        self.created = 0
        self.updated = 0
        self.deactivated = 0
        self.errors = []


def _entry_value(entry, attr):
    return entry[attr].value if attr in entry else None


def _sync_one_entry(entry, result):
    from app.models import ROLE_EMPLOYEE, User

    dn = entry.entry_dn
    username = _entry_value(entry, ATTR_USERNAME)
    email = _entry_value(entry, ATTR_EMAIL)
    name = _entry_value(entry, ATTR_NAME) or username
    uac = _entry_value(entry, ATTR_UAC) or 0
    disabled = bool(int(uac) & UAC_ACCOUNTDISABLE)

    if not email:
        result.errors.append(f"{dn}: no {ATTR_EMAIL} attribute, skipped")
        return
    email = email.strip().lower()

    user = User.query.filter_by(ldap_dn=dn).first() or User.query.filter_by(email=email).first()

    if user is None:
        if disabled:
            return  # never seen before and already disabled -- nothing to do
        user = User(
            name=name,
            email=email,
            role=ROLE_EMPLOYEE,
            active=True,
            ldap_dn=dn,
            ldap_username=username,
            is_ldap_synced=True,
        )
        user.password_hash = generate_password_hash(secrets.token_hex(32))
        db.session.add(user)
        result.created += 1
        return

    # Existing user (matched by ldap_dn, or adopted by matching email):
    # refresh the sync identity, then update each field individually
    # unless an admin has locked it via a manual edit.
    user.ldap_dn = dn
    user.ldap_username = username
    user.is_ldap_synced = True

    just_deactivated = False
    field_changed = False

    if not user.name_locked and user.name != name:
        user.name = name
        field_changed = True
    if not user.email_locked and user.email != email:
        user.email = email
        field_changed = True
    if not disabled and not user.role_locked and user.role != ROLE_EMPLOYEE:
        user.role = ROLE_EMPLOYEE
        field_changed = True
    if not user.active_locked:
        desired_active = not disabled
        if user.active != desired_active:
            user.active = desired_active
            if disabled:
                just_deactivated = True
            else:
                field_changed = True

    if just_deactivated:
        result.deactivated += 1
    elif field_changed:
        result.updated += 1


def run_sync(settings):
    """Bind as the service account, search for users, and create/update/
    deactivate local User rows accordingly. Raises on connection/config
    failure; per-entry problems are collected into result.errors instead
    of aborting the whole sync."""
    _require_config(settings)
    result = SyncResult()

    conn = _connect(settings)
    try:
        conn.search(
            settings.search_base,
            settings.user_filter or "(&(objectCategory=person)(objectClass=user))",
            search_scope="SUBTREE",
            attributes=[ATTR_USERNAME, ATTR_EMAIL, ATTR_NAME, ATTR_UAC],
        )

        for entry in conn.entries:
            try:
                _sync_one_entry(entry, result)
            except Exception as exc:
                result.errors.append(f"{entry.entry_dn}: {exc}")
    finally:
        conn.unbind()

    db.session.commit()
    return result
