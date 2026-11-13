"""Customer portal: auth, role separation, ownership (IDOR) and the end-to-end customer->reviewer flow."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, select
from sqlalchemy.orm import Session

from app.agent.mock_llm import MockLLM
from app.agent.pipeline import Pipeline
from app.api.deps import get_embedder, get_runner
from app.core.config import Settings, get_settings
from app.core.security import (
    hash_password,
    issue_customer_token,
    read_customer_token,
    verify_password,
)
from app.db import models as m
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services.retrieval import NullRetriever
from data_gen.demo_customers import (
    SCENARIOS,
    demo_email,
    ensure_demo_customer_accounts,
    ensure_demo_customers,
)
from tests.conftest import SQLITE_TABLES

REVIEWER_KEY = "reviewer-key-123456"
DEMO_PW = "demo-pass-2026"


class World:
    def __init__(self) -> None:
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine, tables=SQLITE_TABLES)
        with Session(self.engine) as s:
            ensure_demo_customers(s)
            ensure_demo_customer_accounts(s, DEMO_PW)
        self.anon = TestClient(app)
        self.reviewer = TestClient(app, headers={"Authorization": f"Bearer {REVIEWER_KEY}"})

    def login(self, who: int) -> TestClient:
        r = self.anon.post("/portal/login", json={"email": demo_email(SCENARIOS[who]), "password": DEMO_PW})
        assert r.status_code == 200, r.text
        return TestClient(app, headers={"Authorization": f"Bearer {r.json()['token']}"})

    def txns(self, c: TestClient) -> list[dict[str, Any]]:
        return c.get("/portal/transactions").json()  # type: ignore[no-any-return]


@pytest.fixture
def w() -> Iterator[World]:
    from app.api.auth import submit_limiter
    from app.api.portal import login_limiter

    world = World()

    def db() -> Iterator[Session]:
        with Session(world.engine) as s:
            yield s

    def runner() -> Any:
        def run(did: int) -> None:
            with Session(world.engine) as s:
                Pipeline(s, MockLLM(list(s.scalars(select(m.Merchant.name)))), NullRetriever()).run(did)

        return run

    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_runner] = runner
    app.dependency_overrides[get_embedder] = lambda: None
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, reviewer_accounts=f"priya={REVIEWER_KEY}", auth_secret="test-secret-xyz"
    )
    submit_limiter._hits.clear()
    login_limiter._hits.clear()
    yield world
    app.dependency_overrides.clear()


# ---- primitives -----------------------------------------------------------------------------
def test_password_hashing_is_salted_and_verifiable() -> None:
    a, b = hash_password("s3cret-pass"), hash_password("s3cret-pass")
    assert a != b and a.startswith("scrypt$") and "s3cret" not in a
    assert verify_password("s3cret-pass", a) and not verify_password("wrong-pass", a)
    assert not verify_password("x", "garbage")


def test_tokens_cannot_be_forged_tampered_or_reused_after_expiry() -> None:
    t = issue_customer_token(b"k1", 1, 2, now=1000)
    assert read_customer_token(b"k1", t, now=1001)["cid"] == 2  # type: ignore[index]
    assert read_customer_token(b"k2", t, now=1001) is None  # wrong key
    body, sig = t[5:].split(".")
    assert read_customer_token(b"k1", f"cust.{body}x.{sig}", now=1001) is None  # tampered
    assert read_customer_token(b"k1", t, now=1000 + 9 * 3600) is None  # expired
    assert read_customer_token(b"k1", REVIEWER_KEY) is None


# ---- registration / login -------------------------------------------------------------------
def test_register_login_and_profile(w: World) -> None:
    r = w.anon.post("/portal/register", json={"email": "New.User@Example.com", "password": "longenough1", "name": "New User"})
    assert r.status_code == 201 and r.json()["role"] == "customer"
    c = TestClient(app, headers={"Authorization": f"Bearer {r.json()['token']}"})
    me = c.get("/portal/me").json()
    assert me["email"] == "new.user@example.com" and me["cards"] == []
    assert w.anon.post("/portal/register", json={"email": "new.user@example.com", "password": "longenough1", "name": "X Y"}).status_code == 409
    ok = w.anon.post("/portal/login", json={"email": "new.user@example.com", "password": "longenough1"})
    assert ok.status_code == 200 and "password" not in ok.text.lower()


def test_invalid_logins_are_rejected_uniformly(w: World) -> None:
    bad = w.anon.post("/portal/login", json={"email": demo_email(SCENARIOS[0]), "password": "wrong-password"})
    nobody = w.anon.post("/portal/login", json={"email": "nobody@example.com", "password": "wrong-password"})
    assert bad.status_code == nobody.status_code == 401 and bad.json() == nobody.json()
    assert w.anon.post("/portal/login", json={"email": "x", "password": "short"}).status_code == 422


def test_registration_cannot_grant_reviewer_role(w: World) -> None:
    r = w.anon.post("/portal/register", json={"email": "evil@example.com", "password": "longenough1", "name": "Evil", "role": "REVIEWER"})
    assert r.status_code == 201 and r.json()["role"] == "customer"
    c = TestClient(app, headers={"Authorization": f"Bearer {r.json()['token']}"})
    assert c.get("/disputes").status_code == 403


def test_portal_requires_a_customer_token(w: World) -> None:
    assert w.anon.get("/portal/me").status_code == 401
    assert w.reviewer.get("/portal/me").status_code == 401  # reviewer keys are not customer sessions


def test_portal_fails_closed_without_any_secret(w: World) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    assert w.anon.post("/portal/login", json={"email": "a@b.co", "password": "whatever1"}).status_code == 503


# ---- role separation and ownership ---------------------------------------------------------
@pytest.mark.parametrize(
    "method,path",
    [("get", "/disputes"), ("get", "/disputes/1"), ("get", "/metrics"), ("get", "/customers"),
     ("get", "/customers/1/transactions"), ("post", "/disputes/1/review"), ("post", "/disputes/1/process"),
     ("post", "/disputes/1/reopen"), ("post", "/disputes")],
)  # fmt: skip
def test_customers_cannot_use_reviewer_apis(w: World, method: str, path: str) -> None:
    c = w.login(0)
    kw = {"json": {"action": "APPROVE"}} if path.endswith("/review") else {}
    assert getattr(c, method)(path, **kw).status_code == 403


def test_customer_sees_only_own_transactions(w: World) -> None:
    meera, rohan = w.login(0), w.login(1)
    mt, rt = w.txns(meera), w.txns(rohan)
    assert [float(t["amount"]) for t in mt] == [2499.0, 2499.0]
    assert [float(t["amount"]) for t in rt] == [5000.0]
    assert not {t["id"] for t in mt} & {t["id"] for t in rt}


def test_customer_cannot_dispute_someone_elses_transaction(w: World) -> None:
    meera, rohan = w.login(0), w.login(1)
    rohans = w.txns(rohan)[0]["id"]
    r = meera.post("/portal/disputes", json={"transaction_id": rohans, "category": "OTHER", "description": "Not mine at all"})
    assert r.status_code == 404
    r = meera.post("/portal/disputes", json={"transaction_id": 999999, "category": "OTHER", "description": "Not mine at all"})
    assert r.status_code == 404


def test_customer_id_in_body_is_ignored(w: World) -> None:
    meera = w.login(0)
    t = w.txns(meera)[0]["id"]
    r = meera.post("/portal/disputes", json={"transaction_id": t, "category": "CHARGED_TWICE", "description": "Charged twice for one order", "customer_id": 2})
    assert r.status_code == 202
    with Session(w.engine) as s:
        d = s.get(m.Dispute, r.json()["id"])
        meera_id = s.scalars(select(m.Customer.id).where(m.Customer.name == SCENARIOS[0].customer)).one()
        assert d is not None and d.customer_id == meera_id


def test_customer_cannot_read_another_customers_complaint(w: World) -> None:
    meera, rohan = w.login(0), w.login(1)
    t = w.txns(meera)[0]["id"]
    did = meera.post("/portal/disputes", json={"transaction_id": t, "category": "CHARGED_TWICE", "description": "Charged twice"}).json()["id"]
    assert rohan.get(f"/portal/disputes/{did}").status_code == 404
    assert all(x["id"] != did for x in rohan.get("/portal/disputes").json())


def test_invalid_category_and_blank_text_rejected(w: World) -> None:
    meera = w.login(0)
    t = w.txns(meera)[0]["id"]
    assert meera.post("/portal/disputes", json={"transaction_id": t, "category": "PLEASE_REFUND", "description": "abcdef"}).status_code == 422
    assert meera.post("/portal/disputes", json={"transaction_id": t, "category": "OTHER", "description": "     "}).status_code == 422


# ---- end-to-end: customer -> AI pipeline -> reviewer -> customer ----------------------------
def _submit(c: TestClient, w: World, idx: int, category: str) -> int:
    t = w.txns(c)[0]["id"]
    r = c.post("/portal/disputes", json={"transaction_id": t, "category": category, "description": SCENARIOS[idx].complaint})
    assert r.status_code == 202, r.text
    return int(r.json()["id"])


def test_customer_complaint_is_processed_and_visible_to_reviewer(w: World) -> None:
    meera = w.login(0)
    did = _submit(meera, w, 0, "CHARGED_TWICE")
    case = w.reviewer.get(f"/disputes/{did}").json()  # same record, existing pipeline already ran
    assert case["reason_code"] == "DUPLICATE_CHARGE" and case["decision"]["model"] == "mock-rules-v1"
    assert any(i["id"] == did for i in w.reviewer.get("/disputes?status=AUTO_RESOLVED&status=NEEDS_HUMAN&page_size=100").json()["items"])
    mine = meera.get(f"/portal/disputes/{did}").json()
    assert mine["reference"] == f"DIQ-{did:06d}" and mine["merchant"] == "DemoMart Online"
    assert mine["status"] == "APPROVED" and "not confirm that the money has been credited" in mine["message"]
    body = str(mine)
    for secret in ("confidence", "rationale", "evidence", "mock-rules", "injection", "analyst"):
        assert secret not in body.lower(), secret


def test_reviewer_decision_reaches_the_customer(w: World) -> None:
    kavya = w.login(2)
    did = _submit(kavya, w, 2, "NOT_MY_TRANSACTION")
    before = kavya.get(f"/portal/disputes/{did}").json()
    assert before["status"] == "UNDER_REVIEW" and before["letter"] is None
    assert kavya.post(f"/disputes/{did}/review", json={"action": "APPROVE"}).status_code == 403
    r = w.reviewer.post(f"/disputes/{did}/review", json={"action": "OVERRIDE", "final_decision": "FILE_CHARGEBACK", "notes": "Customer called; device was stolen"})
    assert r.status_code == 200
    after = kavya.get(f"/portal/disputes/{did}").json()
    assert after["status"] == "APPROVED" and "chargeback" in after["message"]
    assert after["letter"] is None  # agent's letter was for REJECT; never shown after an override
    assert "stolen" not in str(after)  # reviewer notes stay internal
    assert [t["label"] for t in after["timeline"]][-1] == "Decision: Approved"


def test_reviewer_rejection_reaches_the_customer(w: World) -> None:
    kavya = w.login(2)
    did = _submit(kavya, w, 2, "NOT_MY_TRANSACTION")
    assert w.reviewer.post(f"/disputes/{did}/review", json={"action": "APPROVE"}).status_code == 200
    after = kavya.get(f"/portal/disputes/{did}").json()
    assert after["status"] == "REJECTED" and after["letter"]  # approved agent REJECT: its letter applies


def test_demo_accounts_are_idempotent(w: World) -> None:
    with Session(w.engine) as s:
        assert ensure_demo_customer_accounts(s, "other-password-1") == {"accounts": 0}
    w.login(0)  # original password still valid: existing accounts are never modified
