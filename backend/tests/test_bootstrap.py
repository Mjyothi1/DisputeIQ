"""Startup bootstrap: fills an empty database once and never wipes existing data."""

from sqlalchemy import StaticPool, create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db import models
from app.db.enums import DisputeStatus
from app.db.init_db import init_db
from app.services.cases import QueueFilter, list_disputes
from data_gen.bootstrap import ensure_demo_data


def _factory():  # type: ignore[no-untyped-def]
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    init_db(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_seeds_empty_db_then_keeps_data_on_restart() -> None:
    factory = _factory()
    settings = Settings(llm_provider="gemini", gemini_api_key="")  # backlog must not need a key
    first = ensure_demo_data(factory, settings)
    assert first["seeded"] is True and first["processed"] == 300

    with factory() as s:
        # a live submission and an analyst change made after the first boot
        cust = s.scalars(select(models.Customer)).first()
        assert cust is not None
        s.add(models.Dispute(customer_id=cust.id, channel="FORM", raw_text="live case"))
        s.commit()
        n_before = s.scalar(select(func.count()).select_from(models.Dispute))

    second = ensure_demo_data(factory, settings)  # simulated restart / redeploy
    assert second == {"seeded": False, "processed": 0, "memory": 0}
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(models.Dispute)) == n_before
        assert s.scalar(select(models.Dispute).where(models.Dispute.raw_text == "live case"))
        assert not s.scalars(
            select(models.Dispute).where(
                models.Dispute.split.is_not(None), models.Dispute.status == DisputeStatus.NEW
            )
        ).first()


def test_filed_late_cases_do_not_top_the_urgency_queue() -> None:
    factory = _factory()
    ensure_demo_data(factory, Settings(llm_provider="mock"))
    with factory() as s:
        page = list_disputes(
            s,
            QueueFilter((DisputeStatus.NEEDS_HUMAN,), None, None, None, None, None, "urgency"),
            1,
            1000,
        )
        flags = [i.filed_late for i in page.items]
        assert any(flags) and not flags[0]
        assert flags == sorted(flags)  # every actionable case comes before any filed-late one
        due = list_disputes(
            s,
            QueueFilter((DisputeStatus.NEEDS_HUMAN,), None, None, None, 7, None, "urgency"),
            1,
            100,
        )
        assert not any(i.filed_late for i in due.items)
