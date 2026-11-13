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


# ---- BOOTSTRAP_DEMO_CUSTOMERS: opt-in, additive, idempotent --------------------------------
def _snapshot(factory):  # type: ignore[no-untyped-def]
    with factory() as s:
        return (
            [(c.id, c.name) for c in s.scalars(select(models.Customer).order_by(models.Customer.id))],
            [(t.id, t.amount, t.card_id) for t in s.scalars(select(models.Transaction).order_by(models.Transaction.id))],
            [(d.id, d.status) for d in s.scalars(select(models.Dispute).order_by(models.Dispute.id))],
        )


def test_demo_customers_flag_defaults_off_and_does_nothing() -> None:
    from data_gen.bootstrap import ensure_demo_customers_if_enabled, run_startup_bootstrap

    assert Settings(_env_file=None).bootstrap_demo_customers is False
    factory = _factory()
    off = Settings(_env_file=None)
    assert ensure_demo_customers_if_enabled(factory, off) is None
    run_startup_bootstrap(factory, off)  # both flags off: a normal startup touches nothing
    assert _snapshot(factory) == ([], [], [])


def test_demo_customers_added_once_without_touching_existing_rows() -> None:
    from data_gen.bootstrap import run_startup_bootstrap
    from data_gen.demo_customers import SCENARIOS

    factory = _factory()
    both = Settings(
        _env_file=None, llm_provider="gemini", gemini_api_key="",
        bootstrap_demo_data=True, bootstrap_demo_customers=True,
    )
    base_only = both.model_copy(update={"bootstrap_demo_customers": False})
    run_startup_bootstrap(factory, base_only)
    with factory() as s:
        disputes_before = s.scalar(select(func.count()).select_from(models.Dispute))
    run_startup_bootstrap(factory, both)  # base already seeded, then the six customers are added
    with factory() as s:
        names = set(s.scalars(select(models.Customer.name)))
        assert {sc.customer for sc in SCENARIOS} <= names
        demo_ids = list(s.scalars(select(models.Customer.id).where(models.Customer.name.like("Demo Customer - %"))))
        assert len(demo_ids) == len(SCENARIOS)
        assert s.scalar(select(func.count()).select_from(models.Dispute)) == disputes_before  # no demo disputes
    before = _snapshot(factory)

    run_startup_bootstrap(factory, both)  # a restart with the flag still on
    assert _snapshot(factory) == before  # idempotent: nothing changed, nothing duplicated

    only_customers = Settings(_env_file=None, bootstrap_demo_customers=True)
    run_startup_bootstrap(factory, only_customers)
    assert _snapshot(factory) == before


def test_demo_customers_never_alter_existing_customers() -> None:
    from data_gen.bootstrap import ensure_demo_customers_if_enabled
    from data_gen.demo_customers import SCENARIOS

    factory = _factory()
    with factory() as s:  # a pre-existing customer that happens to share a demo name
        s.add(models.Customer(name=SCENARIOS[0].customer, segment="PREMIUM", phone="+910000000000"))
        s.commit()
    added = ensure_demo_customers_if_enabled(factory, Settings(_env_file=None, bootstrap_demo_customers=True))
    assert added is not None and added["customers"] == len(SCENARIOS) - 1
    with factory() as s:
        c = s.scalars(select(models.Customer).where(models.Customer.name == SCENARIOS[0].customer)).one()
        assert (c.segment, c.phone, len(c.cards)) == ("PREMIUM", "+910000000000", 0)  # untouched


def test_lifespan_runs_bootstrap_only_when_a_flag_is_on(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import asyncio

    import app.main as main_mod

    calls: list[int] = []
    monkeypatch.setattr(main_mod, "_bootstrap_in_background", lambda: calls.append(1))

    async def boot(settings: Settings) -> None:
        monkeypatch.setattr(main_mod, "get_settings", lambda: settings)
        async with main_mod.lifespan(None):  # type: ignore[arg-type]
            pass

    asyncio.run(boot(Settings(_env_file=None)))
    assert calls == []  # normal startup: nothing runs
    asyncio.run(boot(Settings(_env_file=None, bootstrap_demo_customers=True)))
    assert calls == [1]


def test_both_flags_on_empty_db_seed_base_first_then_customers() -> None:
    from data_gen.bootstrap import run_startup_bootstrap

    factory = _factory()
    run_startup_bootstrap(
        factory,
        Settings(_env_file=None, llm_provider="gemini", gemini_api_key="",
                 bootstrap_demo_data=True, bootstrap_demo_customers=True),
    )
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(models.Dispute)) > 0  # base was seeded
        assert s.scalar(select(func.count()).select_from(models.Customer).where(models.Customer.name.like("Demo Customer - %"))) == 6
