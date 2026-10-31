from datetime import datetime, timedelta, timezone
UTC = timezone.utc  # Python 3.11+ compat
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db import models
from app.db.enums import CardNetwork
from app.tools.matching import ClaimFacts, match_transaction, resolve_date
from tests.conftest import NOW, Factory

T0 = NOW - timedelta(days=10)


def facts(**kw: object) -> ClaimFacts:
    base = dict(
        claimed_amount=1000.0, merchant_hint="ShopNow", approx_day=T0.day, approx_month=T0.month
    )
    base.update(kw)
    return ClaimFacts(**base)  # type: ignore[arg-type]


def test_exact_match(factory: Factory, session: Session) -> None:
    t = factory.txn(txn_time=T0)
    factory.txn(txn_time=T0, amount=Decimal("55.00"))
    m = match_transaction(session, factory.customer.id, facts(), NOW)
    assert m.txn is t and m.score == 1.0 and not m.ambiguous


def test_duplicate_pair_picks_the_later_charge(factory: Factory, session: Session) -> None:
    factory.txn(txn_time=T0)
    second = factory.txn(txn_time=T0 + timedelta(minutes=5))
    m = match_transaction(session, factory.customer.id, facts(), NOW)
    assert m.txn is second and not m.ambiguous


def test_misspelled_merchant_and_rounded_amount(factory: Factory, session: Session) -> None:
    t = factory.txn(txn_time=T0, amount=Decimal("1000.40"))
    m = match_transaction(session, factory.customer.id, facts(merchant_hint="ShopNwo"), NOW)
    assert m.txn is t and m.score > 0.85


def test_wrong_date_still_matches_within_window(factory: Factory, session: Session) -> None:
    t = factory.txn(txn_time=T0)
    wrong = T0 + timedelta(days=5)
    m = match_transaction(
        session, factory.customer.id, facts(approx_day=wrong.day, approx_month=wrong.month), NOW
    )
    assert m.txn is t and 0.8 < m.score < 1.0


def test_vague_complaint_cannot_match(factory: Factory, session: Session) -> None:
    factory.txn(txn_time=T0)
    m = match_transaction(session, factory.customer.id, ClaimFacts(merchant_hint="ShopNow"), NOW)
    assert m.txn is None and m.score <= 0.35 + 1e-9


def test_no_signals_no_match(factory: Factory, session: Session) -> None:
    factory.txn()
    assert match_transaction(session, factory.customer.id, ClaimFacts(), NOW).txn is None


def test_ambiguity_flagged_for_distinct_equal_candidates(
    factory: Factory, session: Session
) -> None:
    other = models.Merchant(name="ShopNow2", mcc="5311", category=factory.merchant.category)
    session.add(other)
    session.flush()
    factory.txn(txn_time=T0)
    factory.txn(txn_time=T0, merchant=other)
    m = match_transaction(session, factory.customer.id, facts(), NOW)
    assert m.txn is not None and m.ambiguous


def test_last4_narrows_cards(factory: Factory, session: Session) -> None:
    card2 = models.Card(
        customer=factory.customer,
        masked_pan="XXXX-XXXX-XXXX-2222",
        last4="2222",
        network=CardNetwork.VISA,
    )
    session.add(card2)
    session.flush()
    factory.txn(txn_time=T0)
    t2 = factory.txn(txn_time=T0, card=card2)
    m = match_transaction(session, factory.customer.id, facts(card_last4="2222"), NOW)
    assert m.txn is t2


def test_other_customers_transactions_are_invisible(factory: Factory, session: Session) -> None:
    factory.txn(txn_time=T0)
    stranger = models.Customer(name="Stranger")
    session.add(stranger)
    session.flush()
    assert match_transaction(session, stranger.id, facts(), NOW).txn is None


def test_refund_rows_and_future_rows_excluded(factory: Factory, session: Session) -> None:
    factory.txn(txn_time=T0, amount=Decimal("-1000.00"))
    factory.txn(txn_time=NOW + timedelta(days=30))
    assert match_transaction(session, factory.customer.id, facts(), NOW).txn is None


def test_resolve_date() -> None:
    jan = datetime(2027, 1, 5, tzinfo=UTC)
    assert resolve_date(27, 12, None, jan).year == 2026  # type: ignore[union-attr]
    assert resolve_date(3, 1, None, jan).year == 2027  # type: ignore[union-attr]
    assert resolve_date(30, 2, None, jan) is None
    assert resolve_date(None, 5, None, jan) is None
    assert resolve_date(10, 3, 2025, jan).year == 2025  # type: ignore[union-attr]
