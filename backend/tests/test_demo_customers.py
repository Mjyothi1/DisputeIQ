from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import models
from data_gen.demo_customers import SCENARIOS, ensure_demo_customers


def test_demo_customers_are_isolated_idempotent_and_dispute_free(session: Session) -> None:
    first = ensure_demo_customers(session)
    assert first["customers"] == len(SCENARIOS)
    assert ensure_demo_customers(session) == {"customers": 0, "transactions": 0}  # additive only
    assert session.scalar(select(func.count()).select_from(models.Dispute)) == 0
    for sc in SCENARIOS:
        cust = session.scalars(select(models.Customer).where(models.Customer.name == sc.customer)).one()
        assert len(cust.cards) == 1  # exactly one card per demo customer: no cross-talk
        n = session.scalar(
            select(func.count()).select_from(models.Transaction).where(
                models.Transaction.card_id == cust.cards[0].id
            )
        )
        assert n == (2 if sc.duplicate_after_min else 1)


def test_demo_scenarios_produce_documented_outcomes_with_offline_engine(session: Session) -> None:
    """Offline (mock) check of routing only - this does NOT claim anything about Gemini."""
    from app.agent.mock_llm import MockLLM
    from app.agent.pipeline import Pipeline
    from app.db.enums import DisputeChannel, DisputeStatus
    from app.services.retrieval import NullRetriever

    ensure_demo_customers(session)
    names = list(session.scalars(select(models.Merchant.name)))
    got: dict[str, DisputeStatus] = {}
    for sc in SCENARIOS:
        cust = session.scalars(select(models.Customer).where(models.Customer.name == sc.customer)).one()
        d = models.Dispute(customer_id=cust.id, channel=DisputeChannel.FORM, raw_text=sc.complaint)
        session.add(d)
        session.commit()
        Pipeline(session, MockLLM(names), NullRetriever()).run(d.id)
        session.refresh(d)
        got[sc.key] = d.status
    assert got["duplicate"] is DisputeStatus.AUTO_RESOLVED
    assert got["atm"] is DisputeStatus.AUTO_RESOLVED
    assert got["friendly_fraud"] is DisputeStatus.NEEDS_HUMAN
    assert got["high_value"] is DisputeStatus.NEEDS_HUMAN
    assert got["injection"] is DisputeStatus.NEEDS_HUMAN
