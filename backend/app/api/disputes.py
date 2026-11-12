"""Dispute endpoints: submit, queue, case detail, (re)process, review, audit."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import schemas as s
from app.api.auth import Reviewer, current_reviewer, submit_limiter
from app.api.deps import Runner, get_embedder, get_runner
from app.db import models as m
from app.db.enums import AuditActor, DisputeStatus
from app.db.session import get_db
from app.services.audit import AuditLogger
from app.services.cases import QueueFilter, case_detail, list_disputes
from app.services.embeddings import Embedder
from app.services.review import ReviewError, apply_review

router = APIRouter(
    prefix="/disputes", tags=["disputes"], dependencies=[Depends(current_reviewer)]
)
DB = Annotated[Session, Depends(get_db)]

# Terminal cases (AUTO_RESOLVED, approved, rejected...) are never re-run silently; an analyst
# must reopen an AUTO_RESOLVED case explicitly (POST /{id}/reopen).
PROCESSABLE = (DisputeStatus.NEW, DisputeStatus.NEEDS_HUMAN)


def _get_or_404(db: Session, dispute_id: int) -> m.Dispute:
    d = db.get(m.Dispute, dispute_id)
    if d is None:
        raise HTTPException(404, f"Dispute {dispute_id} not found")
    return d


@router.post("", response_model=s.ProcessAccepted, status_code=202, summary="Submit a complaint")
def submit_dispute(
    body: s.DisputeCreate,
    background: BackgroundTasks,
    db: DB,
    runner: Annotated[Runner, Depends(get_runner)],
    reviewer: Reviewer,
    wait: Annotated[
        bool, Query(description="Run the agent inline and return the final status.")
    ] = False,
) -> s.ProcessAccepted:
    """Create a dispute from complaint text and start the agent (in the background by default)."""
    submit_limiter.check(reviewer)
    if db.get(m.Customer, body.customer_id) is None:
        raise HTTPException(404, f"Customer {body.customer_id} not found")
    d = m.Dispute(customer_id=body.customer_id, channel=body.channel, raw_text=body.raw_text)
    db.add(d)
    db.commit()
    if wait:
        runner(d.id)
        db.refresh(d)
        return s.ProcessAccepted(dispute_id=d.id, status=d.status, message="Processed.")
    background.add_task(runner, d.id)
    return s.ProcessAccepted(
        dispute_id=d.id, status=d.status, message="Accepted; processing started."
    )


@router.get("", response_model=s.DisputePage, summary="Analyst queue")
def queue(
    db: DB,
    status: Annotated[
        list[DisputeStatus] | None, Query(description="Repeat to filter by several")
    ] = None,
    reason_code: str | None = None,
    min_confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
    max_confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
    max_days_to_deadline: Annotated[
        int | None, Query(description="Include overdue; deadline within N days")
    ] = None,
    q: Annotated[
        str | None, Query(max_length=100, description="Search id, customer, merchant or text")
    ] = None,
    sort: Annotated[str, Query(pattern="^(urgency|newest|confidence)$")] = "urgency",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> s.DisputePage:
    """Open cases first, ordered by deadline urgency (soonest first) unless ``sort`` says otherwise."""
    f = QueueFilter(
        status or (), reason_code, min_confidence, max_confidence, max_days_to_deadline, q, sort
    )
    return list_disputes(db, f, page, page_size)


@router.get("/{dispute_id}", response_model=s.CaseDetail, summary="Full case")
def get_case(dispute_id: int, db: DB) -> s.CaseDetail:
    """Complaint (masked), matched transaction, evidence, decision and drafts, reviews, audit timeline."""
    return case_detail(db, _get_or_404(db, dispute_id))


@router.post(
    "/{dispute_id}/process",
    response_model=s.ProcessAccepted,
    status_code=202,
    summary="Run or re-run the agent",
)
def process(
    dispute_id: int,
    background: BackgroundTasks,
    db: DB,
    runner: Annotated[Runner, Depends(get_runner)],
    reviewer: Reviewer,
    wait: bool = False,
) -> s.ProcessAccepted:
    submit_limiter.check(reviewer)
    d = _get_or_404(db, dispute_id)
    if d.status is DisputeStatus.PROCESSING:
        raise HTTPException(409, "Dispute is already being processed.")
    if d.status not in PROCESSABLE:
        raise HTTPException(
            409,
            f"Dispute is {d.status.value}; closed cases are not re-run. "
            "An analyst can reopen an AUTO_RESOLVED case via /reopen.",
        )
    if wait:
        runner(d.id)
        db.refresh(d)
        return s.ProcessAccepted(dispute_id=d.id, status=d.status, message="Processed.")
    background.add_task(runner, d.id)
    return s.ProcessAccepted(
        dispute_id=d.id, status=d.status, message="Accepted; processing started."
    )


@router.post("/{dispute_id}/review", response_model=s.CaseDetail, summary="Analyst review action")
def review(
    dispute_id: int,
    body: s.ReviewIn,
    db: DB,
    reviewer: Reviewer,
    embedder: Annotated[Embedder | None, Depends(get_embedder)],
) -> s.CaseDetail:
    """APPROVE, EDIT (edited drafts), OVERRIDE (different decision, notes required) or REJECT."""
    d = _get_or_404(db, dispute_id)
    try:
        apply_review(db, d, body, reviewer, embedder)
    except ReviewError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    db.refresh(d)
    return case_detail(db, d)


@router.get("/{dispute_id}/audit", response_model=list[s.AuditEventOut], summary="Audit trail")
def audit(dispute_id: int, db: DB) -> list[s.AuditEventOut]:
    _get_or_404(db, dispute_id)
    rows = db.scalars(
        select(m.AuditEvent).where(m.AuditEvent.dispute_id == dispute_id).order_by(m.AuditEvent.id)
    )
    return [s.AuditEventOut.model_validate(r) for r in rows]


@router.post(
    "/{dispute_id}/reopen", response_model=s.CaseDetail, summary="Reopen an auto-resolved case"
)
def reopen(dispute_id: int, body: s.ReopenIn, db: DB, reviewer: Reviewer) -> s.CaseDetail:
    """Exceptional, analyst-only: move an AUTO_RESOLVED case back to human review.

    Previous decisions and audit events are kept; nothing is re-run and no new automatic refund
    recommendation is created.
    """
    d = _get_or_404(db, dispute_id)
    if d.status is not DisputeStatus.AUTO_RESOLVED:
        raise HTTPException(409, f"Only AUTO_RESOLVED cases can be reopened (this is {d.status.value}).")
    d.status = DisputeStatus.NEEDS_HUMAN
    AuditLogger(db, d.id).log(
        "human_reopen", AuditActor.HUMAN, "Case was AUTO_RESOLVED",
        f"{reviewer} reopened for human review. Reason: {body.reason}",
    )
    db.commit()
    db.refresh(d)
    return case_detail(db, d)
