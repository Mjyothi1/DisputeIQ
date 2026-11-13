"""Password hashing and signed customer session tokens (standard library only).

* Passwords: scrypt (n=2**14, r=8, p=1) with a 16-byte random salt; constant-time comparison.
* Customer tokens: ``cust.<payload>.<sig>`` where payload is base64url JSON {sub, cid, role, exp}
  and sig = HMAC-SHA256(secret, payload). The role is fixed to ``customer`` at issue time and is
  re-checked on every request, so it cannot be changed from the client.
* Secret: ``AUTH_SECRET`` (recommended). If unset, a key is derived from ``REVIEWER_ACCOUNTS`` so an
  existing deployment keeps working; with neither set the customer portal is disabled (fail closed).
"""

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from app.core.config import Settings

TOKEN_PREFIX = "cust."
TOKEN_TTL_S = 8 * 3600
_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        got = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32
        )
        return hmac.compare_digest(got.hex(), dk)
    except (ValueError, TypeError):
        return False


def token_secret(settings: Settings) -> bytes | None:
    if settings.auth_secret.strip():
        return settings.auth_secret.strip().encode()
    if settings.reviewer_accounts.strip():
        return hashlib.sha256(
            b"disputeiq-customer-token|" + settings.reviewer_accounts.encode()
        ).digest()
    return None


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_customer_token(
    secret: bytes, account_id: int, customer_id: int, now: float | None = None
) -> str:
    payload = {"sub": account_id, "cid": customer_id, "role": "customer",
               "exp": int((now or time.time()) + TOKEN_TTL_S)}  # fmt: skip
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest())
    return f"{TOKEN_PREFIX}{body}.{sig}"


def read_customer_token(
    secret: bytes, token: str, now: float | None = None
) -> dict[str, Any] | None:
    """The verified payload, or None if malformed, tampered, expired or not a customer token."""
    if not token.startswith(TOKEN_PREFIX):
        return None
    try:
        body, sig = token[len(TOKEN_PREFIX) :].split(".")
        want = _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(want, sig):
            return None
        payload = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if payload.get("role") != "customer" or int(payload.get("exp", 0)) < (now or time.time()):
        return None
    if not isinstance(payload.get("sub"), int) or not isinstance(payload.get("cid"), int):
        return None
    return payload
