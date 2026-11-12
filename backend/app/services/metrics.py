"""Dashboard metrics, computed from the database (and the latest evaluation report, if any)."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import Metrics, RecommendationSummary
from app.core.config import get_settings
from app.core.timeutil import as_utc, utcnow
from app.db import models as m
from app.db.enums import DisputeStatus, ReviewAction
from app.services.cases import OPEN_STATUSES

AT_RISK_DAYS = 7
EVAL_LATEST = Path(__file__).resolve().parents[2] / "eval" / "results" / "latest.json"


def load_latest_eval(path: Path = EVAL_LATEST) -> dict[str, Any] | None:
    """Headline numbers from the last evaluation run, or None if none exists."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data.get("headline") or None


def compute_metrics(
    session: Session, now: datetime | None = None, eval_path: Path | None = None
) -> Metrics:
    now = now or utcnow()
    by_status = {
        k.value: v
        for k, v in session.execute(
            select(m.Dispute.status, func.count()).group_by(m.Dispute.status)
        ).all()
    }
    total = sum(by_status.values())
    processed = session.scalar(select(func.count(func.distinct(m.Decision.dispute_id)))) or 0
    auto = by_status.get(DisputeStatus.AUTO_RESOLVED.value, 0)
    needs = by_status.get(DisputeStatus.NEEDS_HUMAN.value, 0)

    reviews = session.scalars(select(m.Review)).all()
    latest_dec: dict[int, m.Decision] = {
        d.dispute_id: d for d in session.scalars(select(m.Decision).order_by(m.Decision.id))
    }
    overridden = sum(
        1
        for r in reviews
        if r.action is ReviewAction.OVERRIDE
        or (
            r.dispute_id in latest_dec
            and r.final_decision is not latest_dec[r.dispute_id].recommendation
        )
    )

    runs = session.execute(
        select(
            func.count(), func.avg(m.AuditEvent.latency_ms), func.sum(m.AuditEvent.cost_inr)
        ).where(m.AuditEvent.step == "pipeline_complete")
    ).one()
    n_runs, avg_latency_ms, total_cost = runs[0] or 0, runs[1], float(runs[2] or 0)

    deadlines = [
        as_utc(dl)
        for dl in session.scalars(
            select(m.Dispute.deadline_at).where(
                m.Dispute.status.in_(list(OPEN_STATUSES)),
                m.Dispute.deadline_at.is_not(None),
                m.Dispute.deadline_at >= m.Dispute.created_at,  # filed late: no deadline to miss
            )
        )
        if dl is not None
    ]
    overdue = len([dl for dl in deadlines if dl < now])
    at_risk = len([dl for dl in deadlines if now <= dl <= now + timedelta(days=AT_RISK_DAYS)])

    recent_decisions = session.scalars(
        select(m.Decision).order_by(m.Decision.id.desc()).limit(8)
    ).all()
    recent_recs = []
    for d in recent_decisions:
        disp = session.get(m.Dispute, d.dispute_id)
        if disp and disp.customer:
            recent_recs.append(
                RecommendationSummary(
                    dispute_id=disp.id,
                    case_ref=f"DIQ-{disp.id:06d}",
                    recommendation=d.recommendation,
                    rationale=d.rationale,
                    confidence=d.confidence,
                    requires_approval=disp.status not in (
                        DisputeStatus.AUTO_RESOLVED,
                        DisputeStatus.APPROVED,
                        DisputeStatus.REJECTED,
                        DisputeStatus.OVERRIDDEN,
                    ),
                    reason_code=disp.reason_code,
                    customer_name=disp.customer.name,
                )
            )

    by_channel = {
        k.value: v
        for k, v in session.execute(
            select(m.Dispute.channel, func.count()).group_by(m.Dispute.channel)
        ).all()
    }
    suspicious_count = session.scalar(
        select(func.count(m.Dispute.id)).where(
            m.Dispute.reason_code == "FRAUD_NOT_AUTHORISED"
        )
    ) or 0

    settings = get_settings()
    return Metrics(
        cases_total=total, cases_processed=processed, by_status=by_status,
        auto_resolved=auto, auto_resolution_rate=round(auto / processed, 4) if processed else None,
        needs_human=needs, reviewed=len(reviews),
        override_rate=round(overridden / len(reviews), 4) if reviews else None,
        avg_processing_time_s=round(float(avg_latency_ms) / 1000, 3) if avg_latency_ms is not None else None,
        avg_cost_inr=round(total_cost / n_runs, 4) if n_runs else None,
        total_cost_inr=round(total_cost, 4),
        deadline_violations=overdue, deadline_at_risk=at_risk,
        friendly_fraud_flagged=sum(1 for d in latest_dec.values() if d.friendly_fraud_flag),
        injection_flagged=_count_injections(session),
        suspicious_flagged=suspicious_count,
        by_reason_code={k: v for k, v in session.execute(
            select(m.Dispute.reason_code, func.count()).where(m.Dispute.reason_code.is_not(None)).group_by(m.Dispute.reason_code)
        ).all()},
        by_recommendation={k.value: v for k, v in session.execute(
            select(m.Decision.recommendation, func.count()).where(
                m.Decision.id.in_([d.id for d in latest_dec.values()])
            ).group_by(m.Decision.recommendation)
        ).all()},
        by_channel=by_channel,
        recent_recommendations=recent_recs,
        llm_provider_note=(
            "Provider 'mock' is an offline rule-based stand-in; cost and latency are estimates. "
            "Set LLM_PROVIDER=gemini and GEMINI_API_KEY for real Gemini Flash analysis."
            if settings.llm_provider == "mock"
            else (
                f"Live LLM: {settings.llm_provider}"
                + (
                    f" / {settings.gemini_model or settings.llm_model or 'gemini-3.8-flash'} "
                    "(Google free tier; cost recorded as INR 0)."
                    if settings.llm_provider == "gemini"
                    else f" / {settings.llm_model or 'default'}."
                )
            )
        ),
        evaluation=load_latest_eval(eval_path or EVAL_LATEST),
    )  # fmt: skip


def _count_injections(session: Session) -> int:
    n = 0
    for fields in session.scalars(
        select(m.Dispute.extracted_fields).where(m.Dispute.extracted_fields.is_not(None))
    ):
        if fields and fields.get("injection_suspected"):
            n += 1
    return n
