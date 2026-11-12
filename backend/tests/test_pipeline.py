"""End-to-end pipeline tests on a seeded in-memory database (offline mock LLM)."""

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import StaticPool, create_engine, select
from sqlalchemy.orm import Session

from app.agent.llm import LLMError, LLMResult
from app.agent.mock_llm import MockLLM
from app.agent.pipeline import Pipeline, ProcessResult
from app.db import models
from app.db.base import Base
from app.db.enums import AuditActor, DataSplit, DisputeStatus, Recommendation
from app.services.embeddings import HashEmbedder
from app.services.pii import mask_pii
from app.services.retrieval import InMemoryRetriever
from data_gen.generate import generate
from tests.conftest import SQLITE_TABLES

UTC = timezone.utc  # Python 3.11+ compat

NODES = [
    "mask_pii", "intake_extract", "match_transaction", "run_evidence_checks",
    "classify_reason_code", "eligibility_engine", "recommend", "draft_documents", "route",
]  # fmt: skip


@pytest.fixture(scope="module")
def world() -> Iterator[tuple[Session, Pipeline]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine, tables=SQLITE_TABLES)
    s = Session(engine)
    generate(s, seed=11, anchor=datetime(2026, 10, 26, 12, tzinfo=UTC), n_background=1200)
    names = list(s.scalars(select(models.Merchant.name)))
    emb = HashEmbedder(384)
    memory = InMemoryRetriever(emb)
    for d in s.scalars(select(models.Dispute).where(models.Dispute.split == DataSplit.DEV)):
        gt = d.ground_truth or {}
        if gt and not gt.get("prompt_injection"):
            memory.add(d.id, mask_pii(d.raw_text).text, gt["reason_code"], gt["recommendation"])
    yield s, Pipeline(s, MockLLM(names), memory)
    s.close()


def pick(session: Session, scenario: str, **where: Any) -> models.Dispute:
    for d in session.scalars(select(models.Dispute).order_by(models.Dispute.id)):
        gt = d.ground_truth or {}
        if gt.get("scenario") == scenario and all(gt.get(k) == v for k, v in where.items()):
            return d
    raise LookupError(scenario)


def events(s: Session, dispute_id: int) -> list[models.AuditEvent]:
    return list(
        s.scalars(
            select(models.AuditEvent)
            .where(models.AuditEvent.dispute_id == dispute_id)
            .order_by(models.AuditEvent.id)
        )
    )


def test_duplicate_charge_auto_resolves(world: tuple[Session, Pipeline]) -> None:
    s, p = world
    d = pick(s, "duplicate", should_route_human=False)
    r = p.run(d.id)
    assert r.status is DisputeStatus.AUTO_RESOLVED and r.recommendation is Recommendation.REFUND
    assert r.reason_code == "DUPLICATE_CHARGE" and (r.confidence or 0) >= 0.85
    assert r.matched_txn_id == (d.ground_truth or {})["txn_id"]
    s.refresh(d)
    assert d.status is DisputeStatus.AUTO_RESOLVED and d.deadline_at is not None
    assert d.masked_text and d.customer.phone
    assert d.customer.phone not in d.masked_text


def test_every_node_writes_an_audit_event_in_order(world: tuple[Session, Pipeline]) -> None:
    s, p = world
    d = pick(s, "duplicate", should_route_human=False)
    p.run(d.id)
    steps = [e.step for e in events(s, d.id)][-len(NODES) - 1 :]
    assert steps == [*NODES, "pipeline_complete"]
    llm_steps = {e.step for e in events(s, d.id) if e.model}
    assert {"intake_extract", "classify_reason_code", "recommend", "draft_documents"} <= llm_steps
    assert {e.actor for e in events(s, d.id)} == {AuditActor.TOOL, AuditActor.AGENT}
    assert all(e.prompt_version == "v2" for e in events(s, d.id) if e.model)


def test_evidence_and_decision_persisted(world: tuple[Session, Pipeline]) -> None:
    s, p = world
    d = pick(s, "duplicate", should_route_human=False)
    p.run(d.id)
    ev = {e.check_name: e for e in d.evidence}
    assert len(ev) == 7 and ev["duplicate_charge"].result == "PASS"
    dec = d.decisions[-1]
    assert dec.recommendation is Recommendation.REFUND and "Dear" in (
        dec.drafted_customer_letter or ""
    )
    assert dec.drafted_chargeback_filing is None and dec.model == "mock-rules-v1"


def test_friendly_fraud_flagged_and_routed_to_human(world: tuple[Session, Pipeline]) -> None:
    s, p = world
    r = p.run(pick(s, "friendly_fraud").id)
    assert r.status is DisputeStatus.NEEDS_HUMAN and r.friendly_fraud
    assert (
        r.recommendation is Recommendation.REJECT
        and "friendly fraud" in " ".join(r.route_reasons).lower()
    )


def test_genuine_fraud_files_chargeback_with_filing(world: tuple[Session, Pipeline]) -> None:
    s, p = world
    d = pick(s, "genuine_fraud")
    r = p.run(d.id)
    assert (
        r.recommendation is Recommendation.FILE_CHARGEBACK and r.status is DisputeStatus.NEEDS_HUMAN
    )
    assert "CHARGEBACK FILING" in (d.decisions[-1].drafted_chargeback_filing or "")


def test_out_of_window_is_rejected_by_rules_not_llm(world: tuple[Session, Pipeline]) -> None:
    s, p = world
    r = p.run(pick(s, "out_of_window").id)
    assert r.recommendation is Recommendation.REJECT and r.status is DisputeStatus.NEEDS_HUMAN


def test_vague_complaint_asks_for_info(world: tuple[Session, Pipeline]) -> None:
    s, p = world
    d = pick(s, "gnr_vague")
    r = p.run(d.id)
    assert (
        r.recommendation is Recommendation.NEED_MORE_INFO and r.status is DisputeStatus.NEEDS_HUMAN
    )
    assert (r.confidence or 1) < 0.6 and d.decisions[-1].drafted_chargeback_filing is None


def test_all_prompt_injections_flagged_and_never_auto_resolved(
    world: tuple[Session, Pipeline],
) -> None:
    s, p = world
    injected = [
        d
        for d in s.scalars(select(models.Dispute))
        if (d.ground_truth or {}).get("prompt_injection")
    ]
    assert len(injected) == 10
    for d in injected:
        r = p.run(d.id)
        gt = d.ground_truth or {}
        assert r.injection_suspected, d.raw_text
        assert r.status is DisputeStatus.NEEDS_HUMAN
        assert r.recommendation.value == gt["recommendation"], (d.raw_text, r)  # type: ignore[union-attr]


def reopen_for_test(s: Session, *ds: models.Dispute) -> None:
    """Terminal cases are never re-run silently; tests simulate the analyst reopening them."""
    for d in ds:
        d.status = DisputeStatus.NEEDS_HUMAN
    s.commit()


def test_rerun_replaces_evidence_but_keeps_history(world: tuple[Session, Pipeline]) -> None:
    s, p = world
    d = pick(s, "atm_failure")
    p.run(d.id)
    before = len(events(s, d.id))
    reopen_for_test(s, d)
    p.run(d.id)
    s.refresh(d)
    assert len(d.evidence) == 7 and len(d.decisions) >= 2 and len(events(s, d.id)) > before


class FailingLLM:
    model = "failing"

    def structured(self, **_: Any) -> LLMResult[Any]:
        raise LLMError("provider down")


class CrashingLLM:
    model = "crashing"

    def structured(self, **_: Any) -> LLMResult[Any]:
        raise RuntimeError("boom")


def test_llm_outage_degrades_to_human_review_without_crashing(
    world: tuple[Session, Pipeline],
) -> None:
    s, _ = world
    d = pick(s, "duplicate", should_route_human=False)
    reopen_for_test(s, d)
    r = Pipeline(s, FailingLLM()).run(d.id)
    assert r.error is None and r.status is DisputeStatus.NEEDS_HUMAN
    assert r.recommendation is Recommendation.NEED_MORE_INFO
    assert any("failed" in x.lower() for x in r.route_reasons)


def test_unexpected_crash_is_contained_and_audited(world: tuple[Session, Pipeline]) -> None:
    s, _ = world
    d = pick(s, "duplicate", should_route_human=False)
    reopen_for_test(s, d)
    r = Pipeline(s, CrashingLLM()).run(d.id)
    assert r.status is DisputeStatus.NEEDS_HUMAN and r.error == "boom"
    assert events(s, d.id)[-1].step == "pipeline_error"


def test_unknown_dispute_raises(world: tuple[Session, Pipeline]) -> None:
    with pytest.raises(LookupError):
        world[1].run(999_999)


def test_agent_never_reads_ground_truth() -> None:
    """Firewall: no code in app/ may access the ground_truth column (docstrings don't count)."""
    import ast

    offenders = []
    for f in Path("app").rglob("*.py"):
        if f.name == "models.py" or "migrations" in f.parts:
            continue  # the ORM column definition and its migration
        for node in ast.walk(ast.parse(f.read_text())):
            attr = isinstance(node, ast.Attribute) and node.attr == "ground_truth"
            key = isinstance(node, ast.Constant) and node.value == "ground_truth"
            kw = isinstance(node, ast.keyword) and node.arg == "ground_truth"
            if attr or key or kw:
                offenders.append(str(f))
    assert offenders == []


def test_safety_invariants_over_whole_dev_set(world: tuple[Session, Pipeline]) -> None:
    """On all DEV disputes: never auto-resolve what ground truth says needs a human, never
    auto-resolve a wrong recommendation, and keep reason-code accuracy sensible."""
    s, p = world
    dev = list(s.scalars(select(models.Dispute).where(models.Dispute.split == DataSplit.DEV)))
    reopen_for_test(s, *dev)
    results: list[tuple[models.Dispute, ProcessResult]] = [(d, p.run(d.id)) for d in dev]
    auto = [(d, r) for d, r in results if r.status is DisputeStatus.AUTO_RESOLVED]
    assert auto, "expected some auto-resolved cases"
    for d, r in auto:
        gt = d.ground_truth or {}
        assert not gt["should_route_human"], (gt["scenario"], r)
        assert r.recommendation.value == gt["recommendation"]  # type: ignore[union-attr]
    assert all(r.error is None for _, r in results)
    code_acc = sum(
        r.reason_code == (d.ground_truth or {})["reason_code"] for d, r in results
    ) / len(results)
    assert code_acc >= 0.85, code_acc
