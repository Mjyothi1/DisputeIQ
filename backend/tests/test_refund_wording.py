"""No document or customer message may say a refund was processed/credited: there is no payment
integration, so the strongest true statement is 'refund authorised'."""

from datetime import datetime, timezone

import pytest

from app.agent.documents import (
    FALLBACK_BODY,
    DocFacts,
    build_letter,
    claims_completed_refund,
    correct_legacy_refund_wording,
    safe_body,
    validate_llm_text,
)
from app.agent.mock_llm import LETTERS
from app.db import models as m
from app.db.enums import DisputeStatus, Recommendation, ReviewAction
from app.services.customer_view import (
    REFUND_AUTHORISED,
    UNDER_REVIEW_GENERIC,
    UNDER_REVIEW_SUPPORTED,
    customer_status,
    safe_letter,
    timeline,
)

T = datetime(2026, 11, 13, tzinfo=timezone.utc)
FACTS = DocFacts("DIQ-000001", "Meera Iyer", "DemoMart Online", "INR 2,499.00", "10 Nov 2026", "-",
                 "13 Nov 2026", "4021", "VISA", "TXN-1", "ECOM", "OTP_3DS", "5311")  # fmt: skip
OLD_TEMPLATE = ("We have reviewed your dispute about the INR 2,499.00 charge by DemoMart Online on 10 Nov 2026 "
                "(case DIQ-000001). We found the charge was posted more than once or could not be completed, "
                "and we are refunding the amount to your account.")  # fmt: skip


@pytest.mark.parametrize(
    "text",
    [
        "We have processed a refund for this charge.",
        "The amount has been credited to your account.",
        "We are refunding the amount to your account.",
        "Your refund has been processed.",
        "The refund was issued today.",
        "The money will be credited back to your account.",  # still a promise of payment completion
        "We've refunded the duplicate charge.",
        "Refund processed.",
    ],
)
def test_completed_refund_claims_are_detected_and_rejected(text: str) -> None:
    assert claims_completed_refund(text), text
    assert "claims a completed refund" in validate_llm_text(text)
    body, problems = safe_body(text, FALLBACK_BODY[Recommendation.REFUND], FACTS)
    assert problems and not claims_completed_refund(body) and "has been authorised" in body


@pytest.mark.parametrize(
    "text",
    [
        "A refund of the amount has been authorised. The bank will make the payment separately.",
        "Your dispute is currently under review.",
        "We are raising a formal dispute with the merchant on your behalf.",
        "The refund has not been processed by the merchant yet.",  # describes the complaint, not us
    ],
)
def test_truthful_wording_is_allowed(text: str) -> None:
    # 'has not been processed' contains no positive completion claim matched by the guard
    assert not claims_completed_refund(text), text


def test_every_template_and_offline_draft_is_truthful() -> None:
    for rec, body in FALLBACK_BODY.items():
        assert not claims_completed_refund(body), rec
    for rec, body in LETTERS.items():
        assert not claims_completed_refund(body), rec
    refund = build_letter(FACTS, safe_body(None, FALLBACK_BODY[Recommendation.REFUND], FACTS)[0])
    assert "authorised" in refund and "separately" in refund
    assert not any(w in refund.lower() for w in ("processed", "credited", "refunding"))


def test_legacy_letters_are_corrected_on_display() -> None:
    fixed = correct_legacy_refund_wording(OLD_TEMPLATE)
    assert not claims_completed_refund(fixed) and "has been authorised" in fixed
    assert "and and" not in fixed and fixed.startswith("We have reviewed")


# ---- customer-facing status for every backend state -------------------------------------------
def dispute(status: DisputeStatus, rec: Recommendation | None = None, review: tuple[ReviewAction, Recommendation] | None = None,
            letter: str = "letter", edited: str | None = None) -> m.Dispute:  # fmt: skip
    d = m.Dispute(id=1, customer_id=1, raw_text="x", status=status, created_at=T)
    d.decisions = [m.Decision(id=1, recommendation=rec, rationale="internal rationale", confidence=0.9,
                              drafted_customer_letter=letter, created_at=T)] if rec else []  # fmt: skip
    d.reviews = [m.Review(id=1, analyst="priya", action=review[0], final_decision=review[1], notes="INTERNAL NOTE",
                          edited_letter=edited, created_at=T)] if review else []  # fmt: skip
    d.audit_events = []
    return d


R = Recommendation
CASES = [
    ("new", dispute(DisputeStatus.NEW), "SUBMITTED"),
    ("processing", dispute(DisputeStatus.PROCESSING), "PROCESSING"),
    ("review/refund recommended", dispute(DisputeStatus.NEEDS_HUMAN, R.REFUND), "UNDER_REVIEW"),
    ("review/chargeback recommended", dispute(DisputeStatus.NEEDS_HUMAN, R.FILE_CHARGEBACK), "UNDER_REVIEW"),
    ("review/reject recommended", dispute(DisputeStatus.NEEDS_HUMAN, R.REJECT), "UNDER_REVIEW"),
    ("review/need info", dispute(DisputeStatus.NEEDS_HUMAN, R.NEED_MORE_INFO), "UNDER_REVIEW"),
    ("auto refund", dispute(DisputeStatus.AUTO_RESOLVED, R.REFUND, letter=OLD_TEMPLATE), "APPROVED"),
    ("approved refund", dispute(DisputeStatus.APPROVED, R.REFUND, (ReviewAction.APPROVE, R.REFUND)), "APPROVED"),
    ("edited refund", dispute(DisputeStatus.APPROVED, R.REFUND, (ReviewAction.EDIT, R.REFUND), edited="Edited letter"), "APPROVED"),
    ("override chargeback", dispute(DisputeStatus.OVERRIDDEN, R.REJECT, (ReviewAction.OVERRIDE, R.FILE_CHARGEBACK)), "APPROVED"),
    ("override need info", dispute(DisputeStatus.OVERRIDDEN, R.REFUND, (ReviewAction.OVERRIDE, R.NEED_MORE_INFO)), "MORE_INFO"),
    ("rejected", dispute(DisputeStatus.REJECTED, R.REFUND, (ReviewAction.REJECT, R.REJECT)), "REJECTED"),
]


@pytest.mark.parametrize("name,d,code", CASES, ids=[c[0] for c in CASES])
def test_customer_status_never_overstates_and_never_leaks(name: str, d: m.Dispute, code: str) -> None:
    st = customer_status(d)
    assert st.code == code
    shown = " ".join([st.label, st.message, st.letter or "", *[str(t["label"]) for t in timeline(d)]])
    assert not claims_completed_refund(shown), name
    low = shown.lower()
    assert "credited" not in low and "refund processed" not in low and "processed a refund" not in low
    assert "internal note" not in low and "internal rationale" not in low and "priya" not in low


def test_pending_cases_show_review_wording_and_no_letter() -> None:
    sup = customer_status(dispute(DisputeStatus.NEEDS_HUMAN, R.REFUND))
    assert sup.message == UNDER_REVIEW_SUPPORTED and sup.letter is None and sup.label == "Under review"
    gen = customer_status(dispute(DisputeStatus.NEEDS_HUMAN, R.REJECT))
    assert gen.message == UNDER_REVIEW_GENERIC  # never hint at a reject the reviewer hasn't made


def test_approved_refund_says_authorised_not_paid() -> None:
    for d in (CASES[6][1], CASES[7][1]):
        st = customer_status(d)
        assert st.label == "Refund authorised" and st.message == REFUND_AUTHORISED
    auto = customer_status(CASES[6][1])
    assert auto.letter and "has been authorised" in auto.letter  # legacy wording corrected


def test_reviewer_edit_that_claims_payment_is_withheld_from_customer() -> None:
    st = customer_status(dispute(DisputeStatus.APPROVED, R.REFUND, (ReviewAction.EDIT, R.REFUND),
                                 edited="Good news: the amount has been credited to your account."))  # fmt: skip
    # the unsafe edit is never shown; the customer gets the safe final letter instead
    assert st.code == "APPROVED" and st.letter and "has been authorised" in st.letter
    assert not claims_completed_refund(st.letter) and "credited to your account" not in st.letter
    assert safe_letter(None) is None


def test_reviewer_case_view_shows_corrected_legacy_draft() -> None:
    from app.services.cases import _decision_out

    dec = m.Decision(id=1, dispute_id=1, recommendation=R.REFUND, rationale="r", confidence=0.9,
                     friendly_fraud_flag=False, drafted_customer_letter=OLD_TEMPLATE, created_at=T)  # fmt: skip
    out = _decision_out(dec)
    assert out is not None and not claims_completed_refund(out.drafted_customer_letter)
    assert dec.drafted_customer_letter == OLD_TEMPLATE  # stored row untouched


def test_pipeline_replaces_a_model_letter_that_claims_payment(session, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Even if the model writes 'we have processed your refund', the stored draft says authorised."""
    from sqlalchemy import select

    from app.agent import mock_llm
    from app.agent.mock_llm import MockLLM
    from app.agent.pipeline import Pipeline
    from app.db.enums import DisputeChannel
    from app.services.retrieval import NullRetriever
    from data_gen.demo_customers import SCENARIOS, ensure_demo_customers

    monkeypatch.setitem(mock_llm.LETTERS, "REFUND", "Good news, we have processed your refund for case {case_id}.")
    ensure_demo_customers(session)
    names = list(session.scalars(select(m.Merchant.name)))
    for sc in (SCENARIOS[0], SCENARIOS[3]):  # Meera (auto-resolves) and Arjun (refund, needs human)
        cust = session.scalars(select(m.Customer).where(m.Customer.name == sc.customer)).one()
        d = m.Dispute(customer_id=cust.id, channel=DisputeChannel.FORM, raw_text=sc.complaint)
        session.add(d)
        session.commit()
        Pipeline(session, MockLLM(names), NullRetriever()).run(d.id)
        session.refresh(d)
        dec = max(d.decisions, key=lambda x: x.id)
        assert dec.recommendation is Recommendation.REFUND
        assert not claims_completed_refund(dec.drafted_customer_letter), sc.key
        if sc.key == "high_value":  # pending: under review, recommended not approved
            assert "currently under review" in (dec.drafted_customer_letter or "")
            assert "recommended; it has not yet been approved" in (dec.drafted_customer_letter or "")
        else:  # auto-resolved: authorised
            assert "has been authorised" in (dec.drafted_customer_letter or "")
        drafted = next(e for e in d.audit_events if e.step == "draft_documents")
        assert "claims a completed refund" in (drafted.output_summary or "")
        if sc.key == "high_value":
            assert d.status is DisputeStatus.NEEDS_HUMAN
            assert customer_status(d).message == UNDER_REVIEW_SUPPORTED
