"""Supporting endpoints: customers (for the demo submit page), reason codes, metrics."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api import schemas as s
from app.api.auth import Reviewer, current_reviewer
from app.db import models as m
from app.db.session import get_db
from app.rules.config import get_rules_config
from app.services.metrics import AT_RISK_DAYS, compute_metrics

router = APIRouter(tags=["meta"])
DB = Annotated[Session, Depends(get_db)]


@router.get(
    "/customers", dependencies=[Depends(current_reviewer)], response_model=list[s.CustomerOut], summary="List customers (demo helper)"
)
def customers(
    db: DB,
    q: Annotated[str | None, Query(max_length=60)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[s.CustomerOut]:
    """Lets the Submit Complaint page simulate a customer channel. Cards are shown masked."""
    stmt = (
        select(m.Customer)
        .options(selectinload(m.Customer.cards))
        .order_by(m.Customer.name)
        .limit(limit)
    )
    if q:
        stmt = stmt.where(m.Customer.name.ilike(f"%{q}%"))
    return [
        s.CustomerOut(
            id=c.id,
            name=c.name,
            segment=c.segment,
            cards=[f"{k.network.value} ending {k.last4}" for k in c.cards],
        )
        for c in db.scalars(stmt)
    ]


@router.get(
    "/customers/{customer_id}/transactions",
    dependencies=[Depends(current_reviewer)],
    response_model=list[s.RecentTxnOut],
    summary="Recent transactions of a customer (demo helper)",
)
def customer_transactions(
    customer_id: int, db: DB, limit: Annotated[int, Query(ge=1, le=50)] = 10
) -> list[s.RecentTxnOut]:
    """Helps the Submit page suggest realistic complaint wording. Shows no PAN, only last4."""
    if db.get(m.Customer, customer_id) is None:
        raise HTTPException(404, "Customer not found")
    stmt = (
        select(m.Transaction)
        .join(m.Card, m.Transaction.card_id == m.Card.id)
        .where(m.Card.customer_id == customer_id)
        .options(joinedload(m.Transaction.merchant), joinedload(m.Transaction.card))
        .order_by(m.Transaction.txn_time.desc(), m.Transaction.id.desc())
        .limit(limit)
    )
    return [
        s.RecentTxnOut(
            id=t.id, merchant_name=t.merchant.name, amount=t.amount,
            txn_time=t.txn_time, card_last4=t.card.last4,
        )
        for t in db.scalars(stmt)
    ]  # fmt: skip


@router.get("/reason-codes", response_model=list[s.ReasonCodeOut], summary="Reason-code taxonomy")
def reason_codes() -> list[s.ReasonCodeOut]:
    """Illustrative taxonomy and windows (see docs); used by the review UI."""
    cfg = get_rules_config()
    return [
        s.ReasonCodeOut(
            code=c,
            description=sp.description,
            window_days=sp.window_days,
            required_evidence=sp.required_evidence,
        )
        for c, sp in cfg.reason_codes.items()
    ]


@router.get(
    "/metrics", response_model=s.Metrics, summary="Dashboard statistics",
    dependencies=[Depends(current_reviewer)],
)
def metrics(db: DB) -> s.Metrics:
    return compute_metrics(db)


@router.get("/config", response_model=s.PublicConfig, summary="Routing thresholds")
def public_config() -> s.PublicConfig:
    from app.agent.llm import resolve_model
    from app.core.config import get_settings

    t = get_rules_config().thresholds
    settings = get_settings()
    return s.PublicConfig(
        auto_confidence=t.auto_confidence,
        auto_max_amount_inr=t.auto_max_amount_inr,
        auto_resolve_codes=t.auto_resolve_codes,
        at_risk_days=AT_RISK_DAYS,
        llm_provider=settings.llm_provider,
        llm_model=resolve_model(settings),
    )


@router.get("/auth/me", summary="Who am I (validates the reviewer key)")
def me(reviewer: Reviewer) -> dict[str, str]:
    return {"name": reviewer}
