"""Demo sign-in personas: Rohan Desai (customer) and priya (reviewer) use the normal auth paths."""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from data_gen.demo_customers import SCENARIOS, demo_email
from tests.test_portal import DEMO_PW, REVIEWER_KEY, World, _submit, w  # noqa: F401  (fixture)

ROHAN = "rohan.desai@demo.disputeiq.test"


def test_rohan_email_matches_seed_and_frontend_constant() -> None:
    assert demo_email(SCENARIOS[1]) == ROHAN and SCENARIOS[1].customer == "Demo Customer - Rohan Desai"
    demo_ts = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "demo.ts"
    assert f'email: "{ROHAN}"' in demo_ts.read_text()
    assert DEMO_PW not in demo_ts.read_text() and REVIEWER_KEY not in demo_ts.read_text()  # no secrets in the bundle


def test_rohan_logs_in_with_the_existing_password_and_sees_only_his_data(w: World) -> None:  # noqa: F811
    r = w.anon.post("/portal/login", json={"email": ROHAN, "password": DEMO_PW})
    assert r.status_code == 200 and r.json()["name"] == "Demo Customer - Rohan Desai" and r.json()["role"] == "customer"
    rohan = w.login(1)
    txns = rohan.get("/portal/transactions").json()
    assert [(t["merchant_name"], float(t["amount"])) for t in txns] == [("DemoBank ATM Andheri West", 5000.0)]
    assert rohan.get("/portal/me").json()["cards"][0]["masked"] == "VISA •••• 5533"
    meera_did = _submit(w.login(0), w, 0, "CHARGED_TWICE")
    assert rohan.get(f"/portal/disputes/{meera_did}").status_code == 404
    assert rohan.get("/portal/disputes").json() == []
    for path in ("/disputes", f"/disputes/{meera_did}", "/metrics", "/customers"):
        assert rohan.get(path).status_code == 403


def test_rohan_atm_complaint_flows_to_priya(w: World) -> None:  # noqa: F811
    rohan = w.login(1)
    did = _submit(rohan, w, 1, "ATM_NO_CASH")
    case = w.reviewer.get(f"/disputes/{did}").json()
    assert case["reason_code"] == "ATM_CASH_NOT_DISPENSED" and case["customer_name"] == "Demo Customer - Rohan Desai"
    mine = rohan.get(f"/portal/disputes/{did}").json()
    assert mine["merchant"] == "DemoBank ATM Andheri West"
    assert rohan.post(f"/disputes/{did}/review", json={"action": "APPROVE"}).status_code == 403


def test_wrong_demo_password_is_rejected(w: World) -> None:  # noqa: F811
    assert w.anon.post("/portal/login", json={"email": ROHAN, "password": "not-the-password"}).status_code == 401


def test_switching_tokens_never_mixes_roles(w: World) -> None:  # noqa: F811
    """A tab that switches holds one credential at a time; each is judged on its own."""
    rohan = w.login(1)
    assert w.reviewer.get("/auth/me").json() == {"name": "priya"}
    assert rohan.get("/auth/me").status_code == 403      # customer token is not a reviewer
    assert w.reviewer.get("/portal/me").status_code == 401  # reviewer key is not a customer session
    assert rohan.get("/portal/me").status_code == 200


def test_demo_login_creates_or_changes_no_records(w: World) -> None:  # noqa: F811
    with Session(w.engine) as s:
        before = (s.query(m.Customer).count(), s.query(m.CustomerAccount).count(), s.query(m.Dispute).count())
    for _ in range(3):
        w.login(1)
        w.reviewer.get("/auth/me")
    with Session(w.engine) as s:
        after = (s.query(m.Customer).count(), s.query(m.CustomerAccount).count(), s.query(m.Dispute).count())
        acct = s.scalars(select(m.CustomerAccount).where(m.CustomerAccount.email == ROHAN)).one()
        assert acct.password_hash.startswith("scrypt$")
    assert before == after
