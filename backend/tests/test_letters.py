"""Regression for production case DIQ-000314 and letter rules in both portals.

DIQ-000314: a repeat Meera complaint, correctly held for human review by the duplicate guard,
whose stored (model-written) draft said "We have processed a refund" and repeated the greeting.
The reviewer portal flagged it but still displayed it. Now the displayed letter is rebuilt.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.documents import (
    build_letter,
    claims_completed_refund,
    clean_body,
    greeting_name,
    is_clean_letter,
)
from app.db import models as m
from tests.test_portal import World, _submit, w  # noqa: F401  (fixture)

GEMINI_LEGACY = (
    "Date: 13 Nov 2026\nTo: Demo Customer - Meera Iyer\nRe: Card dispute\n\nDear Demo,\n\n"
    "Dear Meera,\n\nWe have processed a refund of {amount} for the duplicate charge. "
    "The amount has been credited to your account.\n\nSincerely,\nCard Disputes Team\n\nSincerely,\nCard Disputes Team"
)


def _make_314(w: World) -> int:  # noqa: F811
    meera = w.login(0)
    first = _submit(meera, w, 0, "CHARGED_TWICE")
    second = _submit(meera, w, 0, "CHARGED_TWICE")  # same transaction -> duplicate guard -> human
    case = w.reviewer.get(f"/disputes/{second}").json()
    assert w.reviewer.get(f"/disputes/{first}").json()["status"] == "AUTO_RESOLVED"
    assert case["status"] == "NEEDS_HUMAN"
    assert any("already has another dispute" in r for r in case["route_reasons"])
    with Session(w.engine) as s:  # simulate the unsafe draft stored in production before the fix
        dec = s.scalars(select(m.Decision).where(m.Decision.dispute_id == second)).one()
        dec.drafted_customer_letter = GEMINI_LEGACY
        s.commit()
    return second


def test_diq_000314_reviewer_sees_corrected_pending_letter(w: World) -> None:  # noqa: F811
    did = _make_314(w)
    c = w.reviewer.get(f"/disputes/{did}").json()
    letter = c["decision"]["drafted_customer_letter"]
    assert not claims_completed_refund(letter)
    assert "processed" not in letter.lower() and "credited" not in letter.lower()
    assert "currently under review" in letter and "recommended; it has not yet been approved" in letter
    assert letter.count("Dear ") == 1 and "Dear Meera," in letter and "Dear Demo" not in letter
    assert letter.count("Sincerely") == 1
    approval = c["letter_on_approval"]
    assert approval and "has been authorised" in approval and "separately" in approval
    assert not claims_completed_refund(approval)
    with Session(w.engine) as s:  # production data is not rewritten
        assert s.scalars(select(m.Decision).where(m.Decision.dispute_id == did)).one().drafted_customer_letter == GEMINI_LEGACY


def test_diq_000314_customer_sees_only_under_review(w: World) -> None:  # noqa: F811
    did = _make_314(w)
    mine = w.login(0).get(f"/portal/disputes/{did}").json()
    assert mine["status"] == "UNDER_REVIEW" and mine["letter"] is None
    assert mine["message"].startswith("Your dispute is currently under review. Our team has identified evidence")
    body = str(mine).lower()
    for leak in ("processed a refund", "credited", "already has another dispute", "duplicate", "recommended", "priya"):
        assert leak not in body, leak


def test_approving_314_sends_the_authorised_letter_not_the_unsafe_draft(w: World) -> None:  # noqa: F811
    did = _make_314(w)
    bad = w.reviewer.post(f"/disputes/{did}/review", json={"action": "EDIT", "edited_letter": "Dear Meera, we have processed your refund."})
    assert bad.status_code == 422 and "authorised" in bad.json()["detail"]
    ok = w.reviewer.post(f"/disputes/{did}/review", json={"action": "APPROVE", "notes": "duplicate verified"})
    assert ok.status_code == 200
    rev_letter = ok.json()["decision"]["drafted_customer_letter"]
    mine = w.login(0).get(f"/portal/disputes/{did}").json()
    assert mine["status_label"] == "Refund authorised"
    for text in (rev_letter, mine["letter"]):
        assert "has been authorised" in text and not claims_completed_refund(text)
        assert text.count("Dear ") == 1 and "Dear Meera," in text
    assert "duplicate verified" not in str(mine)  # notes stay internal


def test_unsafe_auto_resolved_letter_is_rebuilt(w: World) -> None:  # noqa: F811
    meera = w.login(0)
    did = _submit(meera, w, 0, "CHARGED_TWICE")
    with Session(w.engine) as s:
        s.scalars(select(m.Decision).where(m.Decision.dispute_id == did)).one().drafted_customer_letter = GEMINI_LEGACY
        s.commit()
    for text in (w.reviewer.get(f"/disputes/{did}").json()["decision"]["drafted_customer_letter"],
                 meera.get(f"/portal/disputes/{did}").json()["letter"]):  # fmt: skip
        assert is_clean_letter(text) and "has been authorised" in text and "Dear Meera," in text


def test_model_greetings_and_signoffs_are_not_duplicated() -> None:
    from app.services.letters import final_letter
    from tests.test_refund_wording import FACTS

    body = clean_body("Dear Meera,\n\nDear customer,\nWe have reviewed your case.\n\nKind regards,\nThe Bank")
    assert body == "We have reviewed your case."
    letter = build_letter(FACTS, "Dear Meera,\n\nWe have reviewed your case.\n\nSincerely,\nTeam")
    assert letter.count("Dear ") == 1 and letter.count("Sincerely") == 1
    assert greeting_name("Demo Customer - Meera Iyer") == "Meera"
    assert "Dear Meera," in final_letter(FACTS, __import__("app.db.enums", fromlist=["Recommendation"]).Recommendation.REFUND)
