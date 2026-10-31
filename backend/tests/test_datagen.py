from datetime import datetime, timezone
UTC = timezone.utc  # Python 3.11+ compat
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import models
from app.db.enums import DataSplit
from app.rules.eligibility import check_eligibility
from app.rules.policy import baseline_recommendation
from app.tools.evidence import run_all_checks
from data_gen.generate import PLAN, generate

ANCHOR = datetime(2026, 10, 26, 12, tzinfo=UTC)


@pytest.fixture(scope="module")
def seeded() -> Session:
    from sqlalchemy import StaticPool, create_engine

    from app.db.base import Base
    from tests.conftest import SQLITE_TABLES

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine, tables=SQLITE_TABLES)
    s = Session(engine)
    generate(s, seed=7, anchor=ANCHOR)
    return s


def test_sizes(seeded: Session) -> None:
    def n(m: type) -> int:
        return seeded.scalar(select(func.count()).select_from(m)) or 0

    assert n(models.Customer) == 200
    assert n(models.Card) == 300
    assert n(models.Merchant) >= 50
    assert 5000 <= n(models.Transaction) <= 6000
    truthy = seeded.scalar(select(func.count()).where(models.Dispute.ground_truth.is_not(None)))
    assert truthy == sum(PLAN.values()) == 300


def test_split_is_200_100(seeded: Session) -> None:
    counts = dict(
        seeded.execute(
            select(models.Dispute.split, func.count())
            .where(models.Dispute.split.is_not(None))
            .group_by(models.Dispute.split)
        ).all()
    )
    assert counts == {DataSplit.DEV: 200, DataSplit.TEST: 100}


def test_prompt_injection_cases_present_in_both_splits(seeded: Session) -> None:
    inj = [
        d
        for d in seeded.scalars(select(models.Dispute))
        if (d.ground_truth or {}).get("prompt_injection")
    ]
    assert len(inj) == 10 and {d.split for d in inj} == {DataSplit.DEV, DataSplit.TEST}


def test_reproducible() -> None:
    from sqlalchemy import StaticPool, create_engine

    from app.db.base import Base
    from tests.conftest import SQLITE_TABLES

    def texts() -> list[str]:
        e = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(e, tables=SQLITE_TABLES)
        with Session(e) as s:
            generate(s, seed=3, anchor=ANCHOR, n_background=800)
            return [
                d.raw_text for d in s.scalars(select(models.Dispute).order_by(models.Dispute.id))
            ]

    assert texts() == texts()


def test_ground_truth_agrees_with_deterministic_rules(seeded: Session) -> None:
    """The rules + policy engine, given the TRUE reason code, must reproduce ground truth."""
    bad = []
    for d in seeded.scalars(select(models.Dispute).where(models.Dispute.split.is_not(None))):
        gt = d.ground_truth or {}
        txn = seeded.get(models.Transaction, gt["txn_id"])
        assert txn is not None
        exp = Decimal(gt["expected_amount"]) if gt.get("expected_amount") else None
        ev = run_all_checks(seeded, d, txn, d.created_at, exp)
        el = check_eligibility(gt["reason_code"], txn.txn_time, ev, d.created_at)
        score = 0.5 if gt["scenario"] == "gnr_vague" else 0.95
        rec = baseline_recommendation(gt["reason_code"], el, ev, match_score=score).recommendation
        if rec.value != gt["recommendation"]:
            bad.append((d.id, gt["scenario"], gt["recommendation"], rec.value))
    assert not bad, bad[:10]
