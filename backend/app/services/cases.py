"""Read models for the analyst queue and the case-detail page."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, Select, case, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.agent.documents import correct_legacy_refund_wording
from app.api import schemas as s
from app.core.timeutil import as_utc, utcnow
from app.db import models as m
from app.db.enums import DisputeStatus

OPEN_STATUSES = (DisputeStatus.NEW, DisputeStatus.PROCESSING, DisputeStatus.NEEDS_HUMAN)
REVIEWABLE = (DisputeStatus.NEEDS_HUMAN, DisputeStatus.AUTO_RESOLVED)


@dataclass
class QueueFilter:
    statuses: Sequence[DisputeStatus] = ()
    reason_code: str | None = None
    min_confidence: float | None = None
    max_confidence: float | None = None
    max_days_to_deadline: int | None = None
    q: str | None = None
    sort: str = "urgency"  # urgency | newest | confidence


def filed_late(d: m.Dispute) -> bool:
    """True when the dispute window had already closed before the customer raised the dispute."""
    if d.deadline_at is None or d.created_at is None:
        return False
    return as_utc(d.deadline_at) < as_utc(d.created_at)


def days_until(deadline: datetime | None, now: datetime) -> int | None:
    """Whole days left (floored); negative once the deadline has passed."""
    return None if deadline is None else (as_utc(deadline) - as_utc(now)).days


def _conditions(f: QueueFilter, now: datetime) -> list[ColumnElement[bool]]:
    c: list[ColumnElement[bool]] = []
    if f.statuses:
        c.append(m.Dispute.status.in_(list(f.statuses)))
    if f.reason_code:
        c.append(m.Dispute.reason_code == f.reason_code)
    if f.min_confidence is not None:
        c.append(m.Dispute.confidence >= f.min_confidence)
    if f.max_confidence is not None:
        c.append(m.Dispute.confidence <= f.max_confidence)
    if f.max_days_to_deadline is not None:
        c.append(m.Dispute.deadline_at.is_not(None))
        c.append(m.Dispute.deadline_at <= now + timedelta(days=f.max_days_to_deadline))
        c.append(m.Dispute.deadline_at >= m.Dispute.created_at)  # filed late: nothing to chase
    if f.q:
        import re

        q_clean = f.q.strip()
        like = f"%{q_clean}%"
        ors: list[ColumnElement[bool]] = [
            m.Dispute.masked_text.ilike(like),
            m.Dispute.raw_text.ilike(like),
            m.Dispute.reason_code.ilike(like),
            m.Dispute.customer_id.in_(select(m.Customer.id).where(m.Customer.name.ilike(like))),
            m.Dispute.matched_txn_id.in_(
                select(m.Transaction.id)
                .join(m.Merchant, m.Transaction.merchant_id == m.Merchant.id)
                .where(m.Merchant.name.ilike(like))
            ),
        ]
        id_match = re.match(r"(?i)^(?:diq-?)?0*(\d+)$", q_clean)
        if id_match:
            ors.append(m.Dispute.id == int(id_match.group(1)))
        c.append(or_(*ors))
    return c


def _order(stmt: Select, sort: str) -> Select:  # type: ignore[type-arg]
    if sort == "newest":
        return stmt.order_by(m.Dispute.created_at.desc(), m.Dispute.id.desc())
    if sort == "confidence":
        return stmt.order_by(m.Dispute.confidence.asc().nulls_last(), m.Dispute.id)
    open_first = case((m.Dispute.status.in_(list(OPEN_STATUSES)), 0), else_=1)
    # A case whose window had already closed when the customer wrote in has no deadline left to
    # chase; listing it as "most overdue" would bury the cases an analyst can still act on.
    filed_late_last = case((m.Dispute.deadline_at < m.Dispute.created_at, 1), else_=0)
    return stmt.order_by(
        open_first, filed_late_last, m.Dispute.deadline_at.asc().nulls_last(), m.Dispute.id
    )


def list_disputes(
    session: Session, f: QueueFilter, page: int, page_size: int, now: datetime | None = None
) -> s.DisputePage:
    now = now or utcnow()
    conds = _conditions(f, now)
    total = session.scalar(select(func.count()).select_from(m.Dispute).where(*conds)) or 0
    stmt = (
        select(m.Dispute)
        .options(
            joinedload(m.Dispute.customer),
            joinedload(m.Dispute.matched_txn).joinedload(m.Transaction.merchant),
        )
        .where(*conds)
    )
    rows = session.scalars(
        _order(stmt, f.sort).limit(page_size).offset((page - 1) * page_size)
    ).all()
    latest = _latest_decisions(session, [d.id for d in rows])
    items = []
    for d in rows:
        dec = latest.get(d.id)
        txn = d.matched_txn
        items.append(
            s.DisputeSummary(
                id=d.id, customer_name=d.customer.name, channel=d.channel, status=d.status,
                reason_code=d.reason_code, confidence=d.confidence,
                recommendation=dec.recommendation if dec else None,
                friendly_fraud=bool(dec and dec.friendly_fraud_flag),
                merchant=txn.merchant.name if txn else None,
                amount=txn.amount if txn else None,
                deadline_at=d.deadline_at, days_to_deadline=days_until(d.deadline_at, now),
                filed_late=filed_late(d), created_at=d.created_at,
                model=dec.model if dec else None,
            )
        )  # fmt: skip
    return s.DisputePage(items=items, total=total, page=page, page_size=page_size)


def _latest_decisions(session: Session, ids: Sequence[int]) -> dict[int, m.Decision]:
    if not ids:
        return {}
    rows = session.scalars(
        select(m.Decision).where(m.Decision.dispute_id.in_(ids)).order_by(m.Decision.id)
    ).all()
    return {r.dispute_id: r for r in rows}  # later rows overwrite earlier ones


def latest_decision(session: Session, dispute_id: int) -> m.Decision | None:
    return session.scalars(
        select(m.Decision).where(m.Decision.dispute_id == dispute_id).order_by(m.Decision.id.desc())
    ).first()


def _route_reasons(events: Sequence[m.AuditEvent]) -> list[str]:
    """The reasons recorded by the most recent ``route`` audit event."""
    for e in reversed(events):
        if e.step == "route" and e.output_summary and " because: " in e.output_summary:
            return [
                r.strip()
                for r in e.output_summary.split(" because: ", 1)[1].split(" | ")
                if r.strip()
            ]
    return []


def _decision_out(dec: m.Decision | None) -> s.DecisionOut | None:
    """Decision for the reviewer UI. Letters stored before the wording fix are shown corrected, so a
    reviewer never approves a letter that says the refund was already paid (DB row unchanged)."""
    if dec is None:
        return None
    out = s.DecisionOut.model_validate(dec)
    if out.drafted_customer_letter:
        out.drafted_customer_letter = correct_legacy_refund_wording(out.drafted_customer_letter)
    return out


def case_detail(session: Session, d: m.Dispute, now: datetime | None = None) -> s.CaseDetail:
    now = now or utcnow()
    txn = d.matched_txn
    txn_out = None
    if txn is not None:
        txn_out = s.TransactionOut(
            id=txn.id, amount=txn.amount, currency=txn.currency, txn_time=txn.txn_time,
            channel=txn.channel.value, auth_method=txn.auth_method.value, status=txn.status.value,
            refund_status=txn.refund_status.value, is_recurring=txn.is_recurring,
            merchant_name=txn.merchant.name, merchant_category=txn.merchant.category.value,
            merchant_city=txn.merchant.city, card_last4=txn.card.last4, card_network=txn.card.network.value,
        )  # fmt: skip
    audit = sorted(d.audit_events, key=lambda e: e.id)
    dec = latest_decision(session, d.id)
    return s.CaseDetail(
        id=d.id, status=d.status, channel=d.channel, customer_name=d.customer.name,
        customer_segment=d.customer.segment, complaint_masked=d.masked_text,
        extracted_fields=d.extracted_fields, reason_code=d.reason_code, confidence=d.confidence,
        deadline_at=d.deadline_at, days_to_deadline=days_until(d.deadline_at, now),
        filed_late=filed_late(d), created_at=d.created_at, transaction=txn_out,
        evidence=[s.EvidenceOut.model_validate(e) for e in sorted(d.evidence, key=lambda e: e.id)],
        decision=_decision_out(dec),
        reviews=[s.ReviewOut.model_validate(r) for r in sorted(d.reviews, key=lambda r: r.id)],
        route_reasons=_route_reasons(audit),
        can_review=d.status in REVIEWABLE and dec is not None,
        audit=[s.AuditEventOut.model_validate(e) for e in audit],
    )  # fmt: skip
