from app.agent import documents as d
from app.db.enums import Recommendation
from app.rules.types import CheckName, EvidenceItem, Finding

FACTS = d.DocFacts(
    case_id="DIQ-000007", customer_name="Asha Rao", merchant="KartKing", amount="INR 1,499.50",
    txn_date="01 Sep 2026", deadline="29 Dec 2026", received="05 Sep 2026", card_last4="1234",
    network="VISA", txn_ref="TXN-9", channel="ECOM", auth_method="OTP_3DS", mcc="5311",
)  # fmt: skip


def test_validation_rejects_hallucinated_figures() -> None:
    assert d.validate_llm_text("We will refund {amount} for {merchant}.") == []
    assert "literal amount" in d.validate_llm_text("We will refund Rs 500 today")
    assert "literal amount" in d.validate_llm_text("We will refund ₹5,000 today")
    assert "literal date" in d.validate_llm_text("Charged on 12 Oct")
    assert "long number" in d.validate_llm_text("card 4111111111111234")
    assert "unknown placeholder" in d.validate_llm_text("Dear {name}")


def test_safe_body_uses_model_text_when_clean() -> None:
    body, problems = d.safe_body("Refunding {amount} to you.", "fallback", FACTS)
    assert body == "Refunding INR 1,499.50 to you." and problems == []


def test_safe_body_falls_back_when_model_lies_about_money() -> None:
    body, problems = d.safe_body(
        "We will refund Rs 99999 now", d.FALLBACK_BODY[Recommendation.REFUND], FACTS
    )
    assert "99999" not in body and "INR 1,499.50" in body and "literal amount" in problems


def test_safe_body_falls_back_on_empty() -> None:
    body, problems = d.safe_body(None, d.FALLBACK_BODY[Recommendation.REJECT], FACTS)
    assert "unable to raise a dispute" in body and problems == ["empty"]


def test_letter_layout() -> None:
    letter = d.build_letter(FACTS, "Body text.")
    assert (
        "Dear Asha," in letter and "DIQ-000007" in letter and letter.endswith("Card Disputes Team")
    )
    no_txn = d.DocFacts(**{**FACTS.__dict__, "has_txn": False})
    assert "KartKing" not in d.build_letter(no_txn, "x").split("\n")[2]


def test_filing_contains_db_facts_and_evidence() -> None:
    ev = [
        EvidenceItem(CheckName.DUPLICATE_CHARGE, Finding.POSITIVE, "Found 1 matching charge."),
        EvidenceItem(CheckName.ATM_FAILURE, Finding.INCONCLUSIVE, "unknown"),
    ]
    f = d.build_filing(FACTS, "DUPLICATE_CHARGE", ev, "Narrative here")
    assert "TXN-9" in f and "VISA ending 1234" in f and "duplicate_charge: Found 1" in f
    assert "unknown" not in f and "requires analyst approval" in f


def test_formatting_helpers() -> None:
    from decimal import Decimal

    assert d.format_inr(Decimal("1234567.5")) == "INR 1,234,567.50"
    assert d.case_ref(42) == "DIQ-000042"
