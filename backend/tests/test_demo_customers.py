from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
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


# ---- API-level regression: demo customers' transactions are reachable and correctly owned ------
def test_customer_transactions_endpoint_returns_each_demo_customers_own_transactions() -> None:
    from collections.abc import Iterator
    from decimal import Decimal

    from fastapi.testclient import TestClient
    from sqlalchemy import StaticPool, create_engine
    from sqlalchemy.orm import Session as S

    from app.core.config import Settings, get_settings
    from app.db.base import Base
    from app.db.session import get_db
    from app.main import app
    from tests.conftest import SQLITE_TABLES

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=SQLITE_TABLES)
    with S(engine) as s:
        # some unrelated "background" customer with newer-looking history must not leak in
        other = models.Customer(name="Background Person")
        s.add(other)
        s.flush()
        card = models.Card(customer_id=other.id, masked_pan="XXXX-XXXX-XXXX-0001", last4="0001", network="VISA")  # type: ignore[arg-type]
        m = models.Merchant(name="NewsNow Premium", mcc="5994", category="SUBSCRIPTION", city="Pune")  # type: ignore[arg-type]
        s.add_all([card, m])
        s.flush()
        for i in range(12):
            s.add(models.Transaction(card_id=card.id, merchant_id=m.id, amount=Decimal("399"), txn_time=utcnow() - timedelta(days=i), channel="ECOM", auth_method="OTP_3DS"))  # type: ignore[arg-type]
        ensure_demo_customers(s)
        ids = {c.name: c.id for c in s.scalars(select(models.Customer))}

    def override() -> Iterator[S]:
        with S(engine) as sess:
            yield sess

    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, reviewer_accounts="t=test-key-12345")
    try:
        c = TestClient(app, headers={"Authorization": "Bearer test-key-12345"})
        expected = {  # customer -> amounts of their own transactions (per docs/DEMO_PLAN.md)
            "Demo Customer - Meera Iyer": [Decimal("2499"), Decimal("2499")],
            "Demo Customer - Rohan Desai": [Decimal("5000")],
            "Demo Customer - Kavya Nair": [Decimal("8750")],
            "Demo Customer - Arjun Mehta": [Decimal("32000"), Decimal("32000")],
            "Demo Customer - Sana Qureshi": [Decimal("1800"), Decimal("1800")],
            "Demo Customer - Isha Kapoor": [Decimal("999"), Decimal("999")],
        }
        for name, amounts in expected.items():
            rows = c.get(f"/customers/{ids[name]}/transactions?limit=8").json()
            assert sorted(Decimal(str(r["amount"])) for r in rows) == sorted(amounts), name
            assert len({r["id"] for r in rows}) == len(rows)
            assert all(r["merchant_name"] != "NewsNow Premium" for r in rows), name  # no leakage
    finally:
        app.dependency_overrides.clear()
