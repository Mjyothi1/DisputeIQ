"""P1.3: the extraction fallback fills only explicit, unambiguous facts (precision over recall)."""

import pytest

from app.agent.pipeline import _recover_extraction_facts
from app.agent.schemas import ClaimExtraction


def blank(**kw: object) -> ClaimExtraction:
    return ClaimExtraction(claim_type="OTHER", summary="s", **kw)  # type: ignore[arg-type]


def test_atm_complaint_recovery_is_preserved() -> None:
    x = _recover_extraction_facts(
        "I attempted to withdraw ₹20,000 at ATM Anddheri West on 22 Oct. The machine did not "
        "dispense cash but my account was debited.",
        blank(),
    )
    assert (x.claimed_amount, x.approx_day, x.approx_month, x.merchant_hint) == (
        20000.0, 22, 10, "ATM Anddheri West",
    )  # fmt: skip
    assert x.approx_year is None  # never invented


@pytest.mark.parametrize(
    "text",
    [
        "I was not at home.",
        "10 pm and money got cut twice.",
        "2-3 times.",
        "I tried 2-3 times at 10 pm",
        "It happened at least twice, at night",
        "I was at Home when the SMS arrived",
        "money cut 3/4 times",
        "around 5-6 hours back",
    ],
)
def test_no_invented_merchant_or_date(text: str) -> None:
    x = _recover_extraction_facts(text, blank())
    assert (x.merchant_hint, x.approx_day, x.approx_month, x.approx_year) == (None,) * 4, text
    assert x.claimed_amount is None


def test_valid_llm_values_are_never_overwritten() -> None:
    x = _recover_extraction_facts(
        "Paid Rs. 500 at Zomato on 5 Nov 2026",
        blank(claimed_amount=999.0, merchant_hint="Swiggy", approx_day=7, approx_month=3, approx_year=2025),
    )
    assert (x.claimed_amount, x.merchant_hint, x.approx_day, x.approx_month, x.approx_year) == (
        999.0, "Swiggy", 7, 3, 2025,
    )  # fmt: skip


def test_does_not_mix_llm_and_text_dates() -> None:
    x = _recover_extraction_facts("charged on 22 Oct", blank(approx_day=5))
    assert (x.approx_day, x.approx_month) == (5, None)  # disagreement: leave it uncertain


def test_partial_llm_date_completed_only_when_consistent() -> None:
    x = _recover_extraction_facts("charged on 22 Oct", blank(approx_day=22))
    assert (x.approx_day, x.approx_month) == (22, 10)


def test_year_only_when_stated() -> None:
    assert _recover_extraction_facts("on 5/11/2026 at Zomato", blank()).approx_year == 2026
    assert _recover_extraction_facts("on 5/11 at Zomato", blank()).approx_year is None


def test_amount_requires_adjacent_currency_marker() -> None:
    assert _recover_extraction_facts("I called 3 times about 500 units", blank()).claimed_amount is None
    assert _recover_extraction_facts("charged Rs 1,250.50 twice", blank()).claimed_amount == 1250.5
    assert _recover_extraction_facts("charged 800 rupees", blank()).claimed_amount == 800.0
