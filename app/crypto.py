"""Encrypt/decrypt small secrets (currently just the SMTP password) at rest.

Uses cryptography's Fernet (authenticated symmetric encryption) rather than
anything hand-rolled. The key is derived from the app's existing SECRET_KEY
so there's no separate key to generate, store, or rotate. One consequence:
rotating SECRET_KEY makes previously-encrypted values undecryptable (they'd
need re-entering) — acceptable since rotating SECRET_KEY already
invalidates every session anyway.

Requires the 'cryptography' package (not in this project's dependencies
before now — install it in the venv: pip install cryptography). The import
is deliberately deferred into each function rather than done at module
level: app/emailing.py (and therefore app/candidates.py and create_app())
imports this module, so an eager top-level `import cryptography` would
mean the *entire app* fails to boot if the package isn't installed yet,
instead of just email features being unavailable until it is.
"""

import base64
import hashlib


def _fernet():
    from cryptography.fernet import Fernet
    from flask import current_app

    key_material = current_app.config["SECRET_KEY"].encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(key_material).digest())
    return Fernet(key)


def encrypt_secret(plaintext):
    if not plaintext:
        return None
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext):
    if not ciphertext:
        return None
    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None
