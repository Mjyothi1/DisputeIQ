"""API integration tests: real FastAPI app + real pipeline (offline mock LLM) on a seeded SQLite DB."""

import shutil
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
UTC = timezone.utc  # Python 3.11+ compat
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from app.agent.mock_llm import MockLLM
from app.agent.pipeline import Pipeline
from app.api.deps import get_embedder, get_runner
from app.db import models as m
from app.db.base import Base
from app.db.enums import DisputeStatus
from app.db.session import get_db
from app.main import app
from app.services.retrieval import NullRetriever
from data_gen.generate import generate
from tests.conftest import SQLITE_TABLES

ANCHOR = datetime(2026, 10, 26, 12, tzinfo=UTC)


@pytest.fixture(scope="session")
def template_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("tpl") / "template.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine, tables=SQLITE_TABLES)
    with Session(engine) as s:
        generate(s, seed=21, anchor=ANCHOR, n_background=1200)
    engine.dispose()
    return path


class Env:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.calls: list[int] = []
        self.client = TestClient(app)

    def session(self) -> Session:
        return Session(self.engine)

    def runner(self, dispute_id: int) -> None:
        with Session(self.engine) as s:
            names = list(s.scalars(select(m.Merchant.name)))
            Pipeline(s, MockLLM(names), NullRetriever()).run(dispute_id)

    def pick(self, scenario: str, **where: Any) -> int:
        with self.session() as s:
            for d in s.scalars(select(m.Dispute).order_by(m.Dispute.id)):
                gt = d.ground_truth or {}
                if gt.get("scenario") == scenario and all(gt.get(k) == v for k, v in where.items()):
                    return d.id
        raise LookupError(scenario)

    def process(self, dispute_id: int) -> dict[str, Any]:
        r = self.client.post(f"/disputes/{dispute_id}/process?wait=true")
        assert r.status_code == 202, r.text
        return r.json()  # type: ignore[no-any-return]

    def case(self, dispute_id: int) -> dict[str, Any]:
        r = self.client.get(f"/disputes/{dispute_id}")
        assert r.status_code == 200, r.text
        return r.json()  # type: ignore[no-any-return]


@pytest.fixture
def env(template_db: Path, tmp_path: Path) -> Iterator[Env]:
    db = tmp_path / "t.db"
    shutil.copy(template_db, db)
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    e = Env(engine)

    def override_db() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    def recording_runner() -> Callable[[int], None]:
        def run(dispute_id: int) -> None:
            e.calls.append(dispute_id)
            e.runner(dispute_id)

        return run

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_runner] = recording_runner
    app.dependency_overrides[get_embedder] = lambda: None
    yield e
    app.dependency_overrides.clear()
    engine.dispose()


# ---- basics ---------------------------------------------------------------------------------
def test_openapi_documents_all_endpoints(env: Env) -> None:
    paths = env.client.get("/openapi.json").json()["paths"]
    for p in ["/health", "/disputes", "/disputes/{dispute_id}", "/disputes/{dispute_id}/process",
              "/disputes/{dispute_id}/review", "/disputes/{dispute_id}/audit", "/metrics",
              "/customers", "/reason-codes", "/config"]:  # fmt: skip
        assert p in paths, p


def test_public_config(env: Env) -> None:
    cfg = env.client.get("/config").json()
    assert cfg["auto_confidence"] == 0.85 and cfg["auto_max_amount_inr"] == 10000
    assert "DUPLICATE_CHARGE" in cfg["auto_resolve_codes"] and cfg["at_risk_days"] == 7
    assert cfg["llm_provider"] in {"gemini", "mock", "anthropic", "openai"}
    assert isinstance(cfg["llm_model"], str) and cfg["llm_model"]


def test_reason_codes_and_customers(env: Env) -> None:
    codes = env.client.get("/reason-codes").json()
    assert len(codes) == 8 and {c["code"] for c in codes} >= {
        "DUPLICATE_CHARGE",
        "ATM_CASH_NOT_DISPENSED",
    }
    custs = env.client.get("/customers?limit=5").json()
    assert len(custs) == 5 and all("ending" in c for cust in custs for c in cust["cards"])
    name = custs[0]["name"].split()[0]
    assert all(
        name.lower() in c["name"].lower() for c in env.client.get(f"/customers?q={name}").json()
    )


def test_customer_recent_transactions(env: Env) -> None:
    cid = env.client.get("/customers?limit=1").json()[0]["id"]
    txns = env.client.get(f"/customers/{cid}/transactions?limit=5").json()
    assert 0 < len(txns) <= 5
    assert [t["txn_time"] for t in txns] == sorted((t["txn_time"] for t in txns), reverse=True)
    assert all(len(t["card_last4"]) == 4 for t in txns)
    assert env.client.get("/customers/999999/transactions").status_code == 404


# ---- submit ---------------------------------------------------------------------------------
def test_submit_starts_background_processing(env: Env) -> None:
    with env.session() as s:
        cust = s.scalars(select(m.Customer)).first()
        assert cust
        cid = cust.id
    r = env.client.post(
        "/disputes",
        json={"customer_id": cid, "raw_text": "I was charged twice by KartKing for Rs 500"},
    )
    assert r.status_code == 202 and r.json()["status"] in {"NEW", "NEEDS_HUMAN", "AUTO_RESOLVED"}
    assert env.calls == [r.json()["dispute_id"]]  # runner was invoked for the new dispute


def test_submit_validation(env: Env) -> None:
    assert (
        env.client.post(
            "/disputes", json={"customer_id": 999999, "raw_text": "long enough text"}
        ).status_code
        == 404
    )
    assert (
        env.client.post("/disputes", json={"customer_id": 1, "raw_text": "hi"}).status_code == 422
    )
    assert (
        env.client.post("/disputes", json={"customer_id": 1, "raw_text": "x" * 6000}).status_code
        == 422
    )
    assert (
        env.client.post(
            "/disputes", json={"customer_id": 1, "channel": "FAX", "raw_text": "long enough text"}
        ).status_code
        == 422
    )


# ---- process --------------------------------------------------------------------------------
def test_process_duplicate_auto_resolves(env: Env) -> None:
    did = env.pick("duplicate", should_route_human=False)
    out = env.process(did)
    assert out["status"] == "AUTO_RESOLVED"
    c = env.case(did)
    assert c["decision"]["recommendation"] == "REFUND" and c["reason_code"] == "DUPLICATE_CHARGE"
    assert c["can_review"] is True and c["route_reasons"] == []


def test_process_errors(env: Env) -> None:
    assert env.client.post("/disputes/999999/process").status_code == 404
    did = env.pick("duplicate", should_route_human=False)
    with env.session() as s:
        d = s.get(m.Dispute, did)
        assert d
        d.status = DisputeStatus.PROCESSING
        s.commit()
    assert env.client.post(f"/disputes/{did}/process").status_code == 409


def test_process_background_mode(env: Env) -> None:
    did = env.pick("atm_failure")
    r = env.client.post(f"/disputes/{did}/process")
    assert r.status_code == 202 and env.calls == [did]
    assert env.case(did)["status"] in {"AUTO_RESOLVED", "NEEDS_HUMAN"}


# ---- case detail ----------------------------------------------------------------------------
def test_case_detail_shape_and_privacy(env: Env) -> None:
    did = env.pick("friendly_fraud")
    env.process(did)
    r = env.client.get(f"/disputes/{did}")
    c = r.json()
    assert "ground_truth" not in r.text and "raw_text" not in c
    assert c["status"] == "NEEDS_HUMAN" and c["decision"]["friendly_fraud_flag"] is True
    assert c["transaction"]["merchant_name"] and c["transaction"]["card_last4"]
    assert len(c["evidence"]) == 7 and {e["result"] for e in c["evidence"]} <= {
        "PASS",
        "FAIL",
        "INCONCLUSIVE",
        "INFO",
    }
    assert any(
        e["check_name"] == "strong_authentication" and e["result"] == "FAIL" for e in c["evidence"]
    )
    assert "friendly fraud" in " ".join(c["route_reasons"]).lower()
    assert any(r.startswith("Recommendation is REJECT; only REFUND") for r in c["route_reasons"])
    steps = [a["step"] for a in c["audit"]]
    assert steps[0] == "mask_pii" and steps[-1] == "pipeline_complete" and len(steps) == 10
    assert c["days_to_deadline"] is not None
    assert env.client.get("/disputes/999999").status_code == 404


def test_audit_endpoint(env: Env) -> None:
    did = env.pick("duplicate", should_route_human=False)
    assert env.client.get(f"/disputes/{did}/audit").json() == []
    env.process(did)
    events = env.client.get(f"/disputes/{did}/audit").json()
    assert [e["step"] for e in events][0] == "mask_pii" and events[-1]["cost_inr"] is not None
    assert env.client.get("/disputes/999999/audit").status_code == 404


# ---- queue ----------------------------------------------------------------------------------
@pytest.fixture
def processed(env: Env) -> dict[str, int]:
    ids = {
        "dup": env.pick("duplicate", should_route_human=False),
        "ff": env.pick("friendly_fraud"),
        "vague": env.pick("gnr_vague"),
        "oow": env.pick("out_of_window"),
        "atm": env.pick("atm_failure"),
    }
    for i in ids.values():
        env.process(i)
    return ids


def test_queue_filters(env: Env, processed: dict[str, int]) -> None:
    def q(qs: str) -> dict[str, Any]:
        return env.client.get(f"/disputes?{qs}").json()  # type: ignore[no-any-return]

    assert q("status=AUTO_RESOLVED")["total"] >= 1
    both = q("status=AUTO_RESOLVED&status=NEEDS_HUMAN&page_size=100")
    assert {i["id"] for i in both["items"]} >= set(processed.values())
    assert all(i["confidence"] >= 0.85 for i in q("min_confidence=0.85")["items"])
    assert all(i["confidence"] <= 0.5 for i in q("max_confidence=0.5")["items"])
    assert all(
        i["reason_code"] == "DUPLICATE_CHARGE" for i in q("reason_code=DUPLICATE_CHARGE")["items"]
    )
    ff = q(f"q={processed['ff']}")["items"]
    assert processed["ff"] in [i["id"] for i in ff]  # id match (text may match too)
    ffi = next(i for i in ff if i["id"] == processed["ff"])
    name = ffi["customer_name"]
    assert processed["ff"] in [i["id"] for i in q(f"q={name.replace(' ', '%20')}")["items"]]
    merchant = ffi["merchant"]
    assert merchant and processed["ff"] in [
        i["id"] for i in q(f"q={merchant.replace(' ', '%20')}")["items"]
    ]


def test_queue_days_to_deadline_filter(env: Env, processed: dict[str, int]) -> None:
    everything = env.client.get("/disputes?max_days_to_deadline=100000&page_size=100").json()[
        "items"
    ]
    assert everything and all(i["deadline_at"] for i in everything)
    soon = env.client.get("/disputes?max_days_to_deadline=0&page_size=100").json()["items"]
    assert all(i["days_to_deadline"] <= 0 for i in soon)


def test_queue_sorted_by_deadline_urgency_open_cases_first(
    env: Env, processed: dict[str, int]
) -> None:
    items = env.client.get("/disputes?status=NEEDS_HUMAN&page_size=100").json()["items"]
    deadlines = [i["deadline_at"] for i in items if i["deadline_at"]]
    assert deadlines == sorted(deadlines) and len(deadlines) >= 2
    # un-deadlined (e.g. unmatched) cases come after those with deadlines
    flags = [i["deadline_at"] is None for i in items]
    assert flags == sorted(flags)
    allrows = env.client.get("/disputes?page_size=100").json()["items"]
    first_closed = next(
        (k for k, i in enumerate(allrows) if i["status"] in {"AUTO_RESOLVED", "APPROVED"}), None
    )
    open_after = [i for i in allrows[first_closed or 0 :] if i["status"] in {"NEW", "NEEDS_HUMAN"}]
    assert first_closed is None or not open_after


def test_queue_pagination_and_validation(env: Env) -> None:
    p1 = env.client.get("/disputes?page_size=10&page=1").json()
    p2 = env.client.get("/disputes?page_size=10&page=2").json()
    assert p1["total"] >= 300 and len(p1["items"]) == 10 and p1["page"] == 1
    assert {i["id"] for i in p1["items"]}.isdisjoint({i["id"] for i in p2["items"]})
    for bad in ["page_size=101", "page=0", "sort=random", "min_confidence=2", "status=BOGUS"]:
        assert env.client.get(f"/disputes?{bad}").status_code == 422, bad
    assert env.client.get("/disputes?sort=newest&page_size=3").status_code == 200


# ---- review ---------------------------------------------------------------------------------
def review(env: Env, did: int, **body: Any) -> Any:
    return env.client.post(f"/disputes/{did}/review", json={"analyst": "priya", **body})


def test_review_requires_processed_case(env: Env) -> None:
    did = env.pick("friendly_fraud")
    assert review(env, did, action="APPROVE").status_code == 409
    assert review(env, 999999, action="APPROVE").status_code == 404


def test_approve(env: Env, processed: dict[str, int]) -> None:
    r = review(env, processed["ff"], action="APPROVE", notes="agree: authenticated with OTP")
    assert r.status_code == 200
    c = r.json()
    assert c["status"] == "APPROVED" and c["can_review"] is False
    assert c["reviews"][0]["final_decision"] == "REJECT" and c["reviews"][0]["analyst"] == "priya"
    last = c["audit"][-1]
    assert (
        last["step"] == "human_approve"
        and last["actor"] == "HUMAN"
        and "priya" in last["output_summary"]
    )
    assert review(env, processed["ff"], action="APPROVE").status_code == 409  # already decided


def test_vague_case_edited_by_analyst_demo_c(env: Env, processed: dict[str, int]) -> None:
    did = processed["vague"]
    assert review(env, did, action="EDIT").status_code == 422  # nothing edited
    r = review(
        env,
        did,
        action="EDIT",
        edited_letter="Dear customer, please share your order id.",
        notes="asked for order id",
    )
    c = r.json()
    assert r.status_code == 200 and c["status"] == "APPROVED"
    assert c["reviews"][0]["edited_letter"].startswith("Dear customer")
    assert (
        c["decision"]["drafted_customer_letter"] != c["reviews"][0]["edited_letter"]
    )  # agent draft preserved
    assert "Letter edited" in c["audit"][-1]["output_summary"]


def test_override_rules(env: Env, processed: dict[str, int]) -> None:
    did = processed["ff"]  # agent says REJECT
    assert review(env, did, action="OVERRIDE", notes="x").status_code == 422  # no final_decision
    assert (
        review(env, did, action="OVERRIDE", final_decision="FILE_CHARGEBACK").status_code == 422
    )  # no notes
    assert (
        review(env, did, action="OVERRIDE", final_decision="REJECT", notes="same").status_code
        == 422
    )
    assert review(env, did, action="APPROVE", final_decision="REFUND").status_code == 422
    assert review(env, did, action="APPROVE", reason_code="NOT_A_CODE").status_code == 422
    r = review(env, did, action="OVERRIDE", final_decision="FILE_CHARGEBACK", notes="customer's phone was stolen, police report seen",
               reason_code="FRAUD_NOT_AUTHORISED", edited_filing="CHARGEBACK ...")  # fmt: skip
    c = r.json()
    assert (
        r.status_code == 200
        and c["status"] == "OVERRIDDEN"
        and c["reviews"][0]["final_decision"] == "FILE_CHARGEBACK"
    )
    assert "police report" in c["audit"][-1]["output_summary"]


def test_override_can_correct_reason_code(env: Env, processed: dict[str, int]) -> None:
    did = processed["oow"]
    agent_code = env.case(did)["reason_code"]
    other = "NOT_AS_DESCRIBED" if agent_code != "NOT_AS_DESCRIBED" else "GOODS_NOT_RECEIVED"
    r = review(
        env, did, action="OVERRIDE", final_decision="REJECT", reason_code=other, notes="wrong code"
    )
    c = r.json()
    assert (
        r.status_code == 200
        and c["reason_code"] == other
        and f"{agent_code} -> {other}" in c["audit"][-1]["output_summary"]
    )


def test_reject_action(env: Env, processed: dict[str, int]) -> None:
    c = review(env, processed["dup"], action="REJECT", notes="QA: customer withdrew").json()
    assert c["status"] == "REJECTED" and c["reviews"][0]["final_decision"] == "REJECT"


def test_auto_resolved_case_can_still_be_overridden(env: Env, processed: dict[str, int]) -> None:
    c = review(
        env,
        processed["dup"],
        action="OVERRIDE",
        final_decision="NEED_MORE_INFO",
        notes="QA sampling",
    ).json()
    assert c["status"] == "OVERRIDDEN"


def test_cannot_rerun_after_human_decision(env: Env, processed: dict[str, int]) -> None:
    review(env, processed["ff"], action="APPROVE")
    assert env.client.post(f"/disputes/{processed['ff']}/process").status_code == 409


def test_review_validation_errors_are_422(env: Env, processed: dict[str, int]) -> None:
    assert (
        env.client.post(
            f"/disputes/{processed['ff']}/review", json={"action": "APPROVE"}
        ).status_code
        == 422
    )
    assert review(env, processed["ff"], action="DELETE").status_code == 422


# ---- metrics --------------------------------------------------------------------------------
def test_metrics_before_and_after(
    env: Env, processed: dict[str, int], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("app.services.metrics.EVAL_LATEST", tmp_path / "none.json")
    mt = env.client.get("/metrics").json()
    assert mt["cases_total"] >= 300 and mt["cases_processed"] == 5
    assert mt["auto_resolved"] >= 1 and 0 < mt["auto_resolution_rate"] <= 1
    assert (
        mt["avg_processing_time_s"] is not None
        and mt["avg_cost_inr"] > 0
        and mt["total_cost_inr"] > 0
    )
    assert (
        mt["friendly_fraud_flagged"] >= 1
        and mt["override_rate"] is None
        and mt["evaluation"] is None
    )
    assert mt["by_status"]["AUTO_RESOLVED"] == mt["auto_resolved"]
    assert mt["by_recommendation"] and mt["by_reason_code"] and mt["llm_provider_note"]
    review(env, processed["ff"], action="OVERRIDE", final_decision="FILE_CHARGEBACK", notes="n")
    review(env, processed["oow"], action="APPROVE")
    assert env.client.get("/metrics").json()["override_rate"] == 0.5


def test_metrics_includes_evaluation_headline(
    env: Env, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    f = tmp_path / "latest.json"
    f.write_text('{"headline": {"reason_code_accuracy": 0.9}}')
    monkeypatch.setattr("app.services.metrics.EVAL_LATEST", f)
    assert env.client.get("/metrics").json()["evaluation"] == {"reason_code_accuracy": 0.9}
    f.write_text("not json")
    assert env.client.get("/metrics").json()["evaluation"] is None
