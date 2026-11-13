"""Prototype-level reviewer authentication (NOT enterprise SSO).

Reviewers are configured server-side through ``REVIEWER_ACCOUNTS="name=key,name2=key2"``. A
request authenticates with ``Authorization: Bearer <key>``; the reviewer *name* is derived from
the key on the server, never taken from the request body. With no accounts configured every
protected endpoint refuses (fail closed). Keys are compared in constant time.

Limits (documented in docs/SECURITY.md): static shared-secret keys, no expiry/rotation UI, no
per-user audit of failed logins, no MFA. Replace with SSO/OIDC before any real deployment.
"""

import hmac
import threading
import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from app.core.config import Settings, get_settings


def parse_accounts(raw: str) -> dict[str, str]:
    """``"priya=k1, rahul=k2"`` -> ``{"priya": "k1", "rahul": "k2"}`` (bad entries ignored)."""
    out: dict[str, str] = {}
    for part in raw.split(","):
        name, sep, key = part.partition("=")
        name, key = name.strip(), key.strip()
        if sep and name and len(key) >= 8:
            out[name] = key
    return out


def current_reviewer(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Authenticated reviewer name, or 401/503. Used as a dependency on every protected route."""
    accounts = parse_accounts(settings.reviewer_accounts)
    if not accounts:
        raise HTTPException(
            503, "Reviewer access is not configured on the server (set REVIEWER_ACCOUNTS)."
        )
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if token.startswith("cust."):  # a signed-in customer: authenticated, but not a reviewer
        raise HTTPException(403, "Reviewer access required.")
    matched: str | None = None
    for name, key in accounts.items():  # no early exit: constant work per account
        if hmac.compare_digest(key.encode(), token.encode()):
            matched = name
    if matched is None:
        raise HTTPException(
            401, "Invalid or missing reviewer key.", headers={"WWW-Authenticate": "Bearer"}
        )
    return matched


Reviewer = Annotated[str, Depends(current_reviewer)]


class RateLimiter:
    """Tiny in-process sliding-window limiter (per reviewer). Single-instance prototype only."""

    def __init__(self, limit: int, window_s: float) -> None:
        self.limit, self.window_s = limit, window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, who: str) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[who]
            while q and now - q[0] > self.window_s:
                q.popleft()
            if len(q) >= self.limit:
                raise HTTPException(429, "Too many requests; slow down.")
            q.append(now)


submit_limiter = RateLimiter(limit=30, window_s=60)
