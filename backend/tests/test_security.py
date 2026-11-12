"""Auth, duplicate-refund protection, lifecycle rules and input validation (P0.1, P0.2, P1.4)."""


import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.auth import parse_accounts
from app.core.config import Settings, get_settings
from app.db import models as m
from app.db.enums import DisputeStatus
from app.main import app
from tests.test_api import TEST_KEY, Env, env, template_db  # noqa: F401  (fixtures)


def anon(e: Env) -> TestClient:
    return TestClient(app)


# ---- P0.2 auth ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/disputes"), ("get", "/disputes/1"), ("get", "/disputes/1/audit"),
        ("post", "/disputes"), ("post", "/disputes/1/process"), ("post", "/disputes/1/review"),
        ("post", "/disputes/1/reopen"), ("get", "/customers"),
        ("get", "/customers/1/transactions"), ("get", "/metrics"), ("get", "/auth/me"),
    ],
)  # fmt: skip
def test_protected_endpoints_reject_anonymous_and_bad_keys(env: Env, method: str, path: str) -> None:  # noqa: F811
    c = anon(env)
    assert getattr(c, method)(path).status_code == 401
    bad = getattr(c, method)(path, headers={"Authorization": "Bearer wrong-key-000000"})
    assert bad.status_code == 401


def test_public_endpoints_stay_open(env: Env) -> None:  # noqa: F811
    c = anon(env)
    assert c.get("/health").status_code == 200
    assert c.get("/config").status_code == 200
    assert c.get("/reason-codes").status_code == 200


def test_unauthenticated_user_cannot_approve_a_case(env: Env) -> None:  # noqa: F811
    did = env.pick("friendly_fraud")
    env.process(did)
    r = anon(env).post(f"/disputes/{did}/review", json={"analyst": "CEO", "action": "APPROVE"})
    assert r.status_code == 401
    with env.session() as s:
        assert s.scalar(select(m.Review).where(m.Review.dispute_id == did)) is None


def test_fail_closed_when_no_accounts_configured(env: Env) -> None:  # noqa: F811
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, reviewer_accounts="")
    r = env.client.get("/disputes")
    assert r.status_code == 503 and "REVIEWER_ACCOUNTS" in r.json()["detail"]


def test_client_supplied_analyst_name_is_ignored(env: Env) -> None:  # noqa: F811
    did = env.pick("friendly_fraud")
    env.process(did)
    r = env.client.post(f"/disputes/{did}/review", json={"analyst": "Mallory", "action": "APPROVE"})
    assert r.status_code == 200
    assert r.json()["reviews"][0]["analyst"] == "asha"
    assert "Mallory" not in str([e["output_summary"] for e in r.json()["audit"]])


def test_parse_accounts_ignores_short_or_malformed_keys() -> None:
    assert parse_accounts("a=12345678, b=short, junk, =x12345678") == {"a": "12345678"}


def test_auth_me_returns_server_side_name(env: Env) -> None:  # noqa: F811
    assert env.client.get("/auth/me").json() == {"name": "asha"}


def test_oversized_body_rejected(env: Env) -> None:  # noqa: F811
    r = env.client.post("/disputes", content=b"x" * 70_000, headers={"content-type": "application/json"})
    assert r.status_code == 413


# ---- empty complaint ------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["", "     ", "\n\n\n\n\n", "?????", "     a  "])
def test_blank_complaints_rejected(env: Env, text: str) -> None:  # noqa: F811
    with env.session() as s:
        cid = s.scalars(select(m.Customer.id)).first()
    r = env.client.post("/disputes", json={"customer_id": cid, "raw_text": text})
    assert r.status_code == 422


# ---- P1.4 lifecycle -------------------------------------------------------------------------
def _auto_resolved_id(env: Env) -> int:  # noqa: F811
    with env.session() as s:
        for d in s.scalars(select(m.Dispute).order_by(m.Dispute.id)):
            if (d.ground_truth or {}).get("scenario") == "duplicate" and not (
                d.ground_truth or {}
            ).get("should_route_human"):
                env.process(d.id)
                s.refresh(d)
                if d.status is DisputeStatus.AUTO_RESOLVED:
                    return d.id
    pytest.skip("no auto-resolvable case in the seed")


def test_auto_resolved_case_cannot_be_rerun(env: Env) -> None:  # noqa: F811
    did = _auto_resolved_id(env)
    before = env.case(did)
    r = env.client.post(f"/disputes/{did}/process?wait=true")
    assert r.status_code == 409
    after = env.case(did)
    assert after["status"] == "AUTO_RESOLVED" and after["audit"] == before["audit"]


def test_reopen_requires_reason_keeps_history_and_is_audited(env: Env) -> None:  # noqa: F811
    did = _auto_resolved_id(env)
    before = env.case(did)
    assert env.client.post(f"/disputes/{did}/reopen", json={"reason": "short"}).status_code == 422
    r = env.client.post(f"/disputes/{did}/reopen", json={"reason": "Customer called back with new proof"})
    assert r.status_code == 200 and r.json()["status"] == "NEEDS_HUMAN"
    audit = r.json()["audit"]
    assert audit[: len(before["audit"])] == before["audit"]  # history preserved
    assert audit[-1]["step"] == "human_reopen" and "asha" in audit[-1]["output_summary"]
    with env.session() as s:
        n = len(s.scalars(select(m.Decision).where(m.Decision.dispute_id == did)).all())
    assert n == 1  # reopening creates no new automatic decision
    # only AUTO_RESOLVED may be reopened
    assert env.client.post(f"/disputes/{did}/reopen", json={"reason": "second try, not allowed"}).status_code == 409


# ---- P0.1 duplicate refunds -----------------------------------------------------------------
def _clone_dispute(env: Env, did: int) -> int:  # noqa: F811
    """A second, fresh submission with the same complaint text and customer."""
    with env.session() as s:
        orig = s.get(m.Dispute, did)
        assert orig is not None
        d = m.Dispute(customer_id=orig.customer_id, channel=orig.channel, raw_text=orig.raw_text,
                      created_at=orig.created_at)  # fmt: skip
        s.add(d)
        s.commit()
        return d.id


def test_repeat_submission_cannot_auto_refund_same_transaction_twice(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    from app.rules.config import get_rules_config

    monkeypatch.setattr(get_rules_config().thresholds, "frequent_disputer_count", 10_000)
    first = _auto_resolved_id(env)
    txn = env.case(first)["transaction"]["id"]
    second, third = _clone_dispute(env, first), None
    third = _clone_dispute(env, first)
    for did in (second, third):
        env.process(did)
        c = env.case(did)
        if c["transaction"] and c["transaction"]["id"] == txn:
            assert c["status"] == "NEEDS_HUMAN", c["status"]
            assert any("already has another dispute" in r for r in c["route_reasons"])
            assert any(e["step"] == "duplicate_dispute_check" for e in c["audit"])
    with env.session() as s:
        auto = s.scalars(
            select(m.Dispute).where(m.Dispute.matched_txn_id == txn,
                                    m.Dispute.status == DisputeStatus.AUTO_RESOLVED)
        ).all()  # fmt: skip
    assert len(auto) == 1


def test_different_transactions_are_not_blocked(env: Env) -> None:  # noqa: F811
    """Legitimate disputes about different transactions keep their normal routing."""
    ids = []
    with env.session() as s:
        for d in s.scalars(select(m.Dispute).order_by(m.Dispute.id)):
            gt = d.ground_truth or {}
            if gt.get("scenario") == "duplicate" and not gt.get("should_route_human"):
                ids.append(d.id)
            if len(ids) == 2:
                break
    for did in ids:
        env.process(did)
    txns = {env.case(i)["transaction"]["id"] for i in ids if env.case(i)["transaction"]}
    for i in ids:
        assert not any("already has another dispute" in r for r in env.case(i)["route_reasons"])
    assert len(txns) == len(ids)


def test_concurrent_processing_never_yields_two_auto_refunds(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    import threading

    from app.rules.config import get_rules_config

    # Isolate the duplicate guard: the frequent-disputer rule would otherwise also stop clones.
    monkeypatch.setattr(get_rules_config().thresholds, "frequent_disputer_count", 10_000)

    first = _auto_resolved_id(env)
    txn = env.case(first)["transaction"]["id"]
    # reset the original so the race is between fresh submissions only
    with env.session() as s:
        s.get(m.Dispute, first).status = DisputeStatus.NEEDS_HUMAN  # type: ignore[union-attr]
        s.get(m.Dispute, first).matched_txn_id = None  # type: ignore[union-attr]
        s.commit()
    ids = [_clone_dispute(env, first) for _ in range(4)]
    errors: list[BaseException] = []

    def work(i: int) -> None:
        try:
            env.runner(i)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(i,)) for i in ids]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors
    with env.session() as s:
        rows = s.scalars(select(m.Dispute).where(m.Dispute.id.in_(ids))).all()
        on_txn = [d for d in rows if d.matched_txn_id == txn]
        assert sum(d.status is DisputeStatus.AUTO_RESOLVED for d in on_txn) <= 1
        assert len(on_txn) >= 2  # the race really involved the same transaction
        assert all(d.status in (DisputeStatus.AUTO_RESOLVED, DisputeStatus.NEEDS_HUMAN) for d in rows)
