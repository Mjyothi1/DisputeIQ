"""Analyst review: validates the action, records it, updates status, audits it and feeds case memory."""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.api.schemas import ReviewIn
from app.db import models as m
from app.db.enums import AuditActor, DisputeStatus, Recommendation, ReviewAction
from app.services.audit import AuditLogger
from app.services.cases import REVIEWABLE, latest_decision
from app.services.embeddings import Embedder
from app.services.retrieval import index_case

logger = logging.getLogger(__name__)

STATUS_FOR = {
    ReviewAction.APPROVE: DisputeStatus.APPROVED,
    ReviewAction.EDIT: DisputeStatus.APPROVED,
    ReviewAction.OVERRIDE: DisputeStatus.OVERRIDDEN,
    ReviewAction.REJECT: DisputeStatus.REJECTED,
}


@dataclass
class ReviewError(Exception):
    status_code: int
    detail: str


def apply_review(
    session: Session, dispute: m.Dispute, payload: ReviewIn, embedder: Embedder | None = None
) -> m.Review:
    """Record a human decision. Raises :class:`ReviewError` for invalid state or input."""
    decision = latest_decision(session, dispute.id)
    if decision is None:
        raise ReviewError(409, "Dispute has not been processed yet; nothing to review.")
    if dispute.status not in REVIEWABLE:
        raise ReviewError(409, f"Dispute is {dispute.status.value}; it cannot be reviewed now.")

    agent_rec = decision.recommendation
    if payload.action is ReviewAction.REJECT:
        final = Recommendation.REJECT
    elif payload.action is ReviewAction.OVERRIDE:
        assert payload.final_decision is not None  # guaranteed by schema validation
        final = payload.final_decision
        if final is agent_rec and payload.reason_code in (None, dispute.reason_code):
            raise ReviewError(422, "OVERRIDE must change the recommendation or the reason code.")
    else:  # APPROVE / EDIT keep the agent's recommendation
        if payload.final_decision not in (None, agent_rec):
            raise ReviewError(
                422, f"{payload.action.value} cannot change the decision; use OVERRIDE."
            )
        final = agent_rec

    previous_code = dispute.reason_code
    if payload.reason_code:
        dispute.reason_code = payload.reason_code

    review = m.Review(
        dispute_id=dispute.id, analyst=payload.analyst, action=payload.action, final_decision=final,
        notes=payload.notes, edited_letter=payload.edited_letter, edited_filing=payload.edited_filing,
    )  # fmt: skip
    session.add(review)
    dispute.status = STATUS_FOR[payload.action]

    changed = (
        f" (reason code {previous_code} -> {dispute.reason_code})"
        if payload.reason_code and payload.reason_code != previous_code
        else ""
    )
    AuditLogger(session, dispute.id).log(
        f"human_{payload.action.value.lower()}", AuditActor.HUMAN,
        f"Agent recommended {agent_rec.value} @ {decision.confidence:.2f}",
        f"{payload.analyst}: {payload.action.value} -> final decision {final.value}{changed}."
        + (f" Notes: {payload.notes}" if payload.notes else "")
        + (" Letter edited." if payload.edited_letter else "")
        + (" Filing edited." if payload.edited_filing else ""),
    )  # fmt: skip
    session.flush()
    _remember(session, dispute, final, embedder)
    session.commit()
    return review


def _remember(
    session: Session, dispute: m.Dispute, final: Recommendation, embedder: Embedder | None
) -> None:
    """Add the resolved case to similar-case memory (Postgres only; best effort)."""
    if embedder is None or not dispute.masked_text or not dispute.reason_code:
        return
    if session.get_bind().dialect.name != "postgresql":
        return
    try:
        with session.begin_nested():
            index_case(
                session, embedder, dispute.id, dispute.masked_text, dispute.reason_code, final.value
            )
    except Exception:  # memory is an enhancement; never block a human decision
        logger.exception("could not index resolved case", extra={"dispute_id": dispute.id})
