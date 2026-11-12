"""Transaction-level duplicate-dispute protection.

A card transaction must never be auto-refunded twice. When the agent is about to route a case it
(1) takes a per-transaction lock and (2) looks for *other* disputes already tied to the same
transaction. Any hit forces human review - including earlier rejected ones, because a repeat
complaint about a transaction we already ruled on is exactly the ambiguous case a human decides.

The lock covers check -> decision -> commit, so two concurrent submissions serialise: the first
may auto-resolve, the second then sees it and escalates. Postgres uses a transaction-scoped
advisory lock (works across Render instances); every dialect also takes an in-process striped
lock (enough for SQLite and single-instance deployments).
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import models as m

_STRIPES = [threading.Lock() for _ in range(64)]
_ADVISORY_NAMESPACE = 7001


def dispute_ref(dispute_id: int) -> str:
    return f"DIQ-{dispute_id:06d}"


@contextmanager
def transaction_guard(session: Session, txn_id: int) -> Iterator[None]:
    """Serialise decision-making for one transaction. Commit before leaving the block."""
    lock = _STRIPES[txn_id % len(_STRIPES)]
    with lock:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_xact_lock(:ns, :k)"),
                {"ns": _ADVISORY_NAMESPACE, "k": txn_id},
            )
        yield


def other_disputes(session: Session, dispute_id: int, txn_id: int) -> list[m.Dispute]:
    """Other disputes already matched to the same transaction (any status)."""
    return list(
        session.scalars(
            select(m.Dispute)
            .where(m.Dispute.matched_txn_id == txn_id, m.Dispute.id != dispute_id)
            .order_by(m.Dispute.id)
        )
    )
