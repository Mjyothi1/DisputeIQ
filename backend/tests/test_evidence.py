from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db import models
from app.db.enums import (
    AuthMethod,
    RefundStatus,
    SubscriptionStatus,
    TxnChannel,
    TxnStatus,
)
from app.rules.types import CheckName, Finding
from app.tools import evidence as ev
from tests.conftest import NOW, Factory


# ---- duplicates -------------------------------------------------------------------------
def test_duplicate_found_within_window(factory: Factory, session: Session) -> None:
    a = factory.txn()
    b = factory.txn(txn_time=NOW + timedelta(minutes=3))
    r = ev.find_duplicates(session, a)
    assert r.finding is Finding.POSITIVE and r.details["duplicate_txn_ids"] == [b.id]


def test_duplicate_outside_window(factory: Factory, session: Session) -> None:
    a = factory.txn()
    factory.txn(txn_time=NOW + timedelta(hours=25))
    assert ev.find_duplicates(session, a).finding is Finding.NEGATIVE


def test_duplicate_window_boundary_inclusive(factory: Factory, session: Session) -> None:
    a = factory.txn()
    factory.txn(txn_time=NOW + timedelta(hours=24))
    assert ev.find_duplicates(session, a).finding is Finding.POSITIVE


def test_duplicate_requires_same_amount_merchant_card(factory: Factory, session: Session) -> None:
    a = factory.txn()
    other_merchant = models.Merchant(name="Other", mcc="5311", category=factory.merchant.category)
    session.add(other_merchant)
    session.flush()
    factory.txn(amount=Decimal("1000.01"))
    factory.txn(merchant=other_merchant)
    assert ev.find_duplicates(session, a).finding is Finding.NEGATIVE


def test_failed_transactions_are_not_duplicates(factory: Factory, session: Session) -> None:
    a = factory.txn()
    factory.txn(status=TxnStatus.FAILED)
    assert ev.find_duplicates(session, a).finding is Finding.NEGATIVE


def test_single_transaction_has_no_duplicate(factory: Factory, session: Session) -> None:
    assert ev.find_duplicates(session, factory.txn()).finding is Finding.NEGATIVE


# ---- authentication ---------------------------------------------------------------------
def test_authentication_strong_and_weak(factory: Factory) -> None:
    assert (
        ev.check_authentication(factory.txn(auth_method=AuthMethod.OTP_3DS)).finding
        is Finding.POSITIVE
    )
    assert (
        ev.check_authentication(factory.txn(auth_method=AuthMethod.PIN)).finding is Finding.POSITIVE
    )
    assert (
        ev.check_authentication(factory.txn(auth_method=AuthMethod.NONE)).finding
        is Finding.NEGATIVE
    )


# ---- refunds ----------------------------------------------------------------------------
def test_refund_none(factory: Factory, session: Session) -> None:
    assert ev.check_refund_issued(session, factory.txn()).finding is Finding.NEGATIVE


def test_refund_status_full_and_partial(factory: Factory, session: Session) -> None:
    full = ev.check_refund_issued(session, factory.txn(refund_status=RefundStatus.FULL))
    part = ev.check_refund_issued(session, factory.txn(refund_status=RefundStatus.PARTIAL))
    assert full.details["refund_status"] == "FULL"
    assert part.details["refund_status"] == "PARTIAL" and part.finding is Finding.POSITIVE


def test_reversed_transaction_counts_as_full_refund(factory: Factory, session: Session) -> None:
    r = ev.check_refund_issued(session, factory.txn(status=TxnStatus.REVERSED))
    assert r.finding is Finding.POSITIVE and r.details["refund_status"] == "FULL"


def test_refund_transaction_detected(factory: Factory, session: Session) -> None:
    t = factory.txn()
    refund = factory.txn(amount=-t.amount, txn_time=NOW + timedelta(days=2))
    r = ev.check_refund_issued(session, t)
    assert r.finding is Finding.POSITIVE and r.details["refund_txn_ids"] == [refund.id]


# ---- subscriptions ----------------------------------------------------------------------
def _sub(factory: Factory, session: Session, **kw: object) -> models.Subscription:
    s = models.Subscription(card_id=factory.card.id, merchant_id=factory.merchant.id, **kw)
    session.add(s)
    session.flush()
    return s


def test_subscription_cancelled_before_charge(factory: Factory, session: Session) -> None:
    _sub(
        factory, session, status=SubscriptionStatus.CANCELLED, cancelled_at=NOW - timedelta(days=5)
    )
    assert ev.check_subscription_cancelled(session, factory.txn()).finding is Finding.POSITIVE


def test_subscription_cancelled_after_charge_is_negative(
    factory: Factory, session: Session
) -> None:
    _sub(
        factory, session, status=SubscriptionStatus.CANCELLED, cancelled_at=NOW + timedelta(days=1)
    )
    assert ev.check_subscription_cancelled(session, factory.txn()).finding is Finding.NEGATIVE


def test_subscription_active_is_negative(factory: Factory, session: Session) -> None:
    _sub(factory, session, status=SubscriptionStatus.ACTIVE)
    assert ev.check_subscription_cancelled(session, factory.txn()).finding is Finding.NEGATIVE


def test_no_subscription_is_inconclusive(factory: Factory, session: Session) -> None:
    assert ev.check_subscription_cancelled(session, factory.txn()).finding is Finding.INCONCLUSIVE


# ---- dispute history --------------------------------------------------------------------
def test_dispute_history_counts_only_lookback_and_others(
    factory: Factory, session: Session
) -> None:
    current = factory.dispute()
    for days in (10, 100, 300):
        factory.dispute(created_at=NOW - timedelta(days=days))
    factory.dispute(created_at=NOW - timedelta(days=400))  # outside lookback
    r = ev.check_dispute_history(session, current, NOW)
    assert r.details["prior_disputes"] == 3 and r.finding is Finding.POSITIVE


def test_dispute_history_below_threshold(factory: Factory, session: Session) -> None:
    current = factory.dispute()
    factory.dispute(created_at=NOW - timedelta(days=10))
    r = ev.check_dispute_history(session, current, NOW)
    assert r.details["prior_disputes"] == 1 and r.finding is Finding.NEGATIVE


# ---- ATM --------------------------------------------------------------------------------
def test_atm_failure_positive(factory: Factory) -> None:
    t = factory.txn(channel=TxnChannel.ATM, details={"cash_dispensed": False}, account_debited=True)
    assert ev.check_atm_failure(t).finding is Finding.POSITIVE


def test_atm_cash_dispensed_negative(factory: Factory) -> None:
    t = factory.txn(channel=TxnChannel.ATM, details={"cash_dispensed": True})
    assert ev.check_atm_failure(t).finding is Finding.NEGATIVE


def test_atm_not_debited_negative(factory: Factory) -> None:
    t = factory.txn(
        channel=TxnChannel.ATM, details={"cash_dispensed": False}, account_debited=False
    )
    assert ev.check_atm_failure(t).finding is Finding.NEGATIVE


def test_atm_unknown_dispense_inconclusive(factory: Factory) -> None:
    assert ev.check_atm_failure(factory.txn(channel=TxnChannel.ATM)).finding is Finding.INCONCLUSIVE


def test_non_atm_is_negative(factory: Factory) -> None:
    assert ev.check_atm_failure(factory.txn()).finding is Finding.NEGATIVE


# ---- amount mismatch --------------------------------------------------------------------
def test_amount_mismatch(factory: Factory) -> None:
    t = factory.txn(amount=Decimal("1200.00"))
    r = ev.check_amount_mismatch(t, Decimal("1000.00"))
    assert r.finding is Finding.POSITIVE and r.details["difference"] == "200.00"
    assert ev.check_amount_mismatch(t, Decimal("1200.00")).finding is Finding.NEGATIVE
    assert ev.check_amount_mismatch(t, None).finding is Finding.INCONCLUSIVE


# ---- run_all ----------------------------------------------------------------------------
def test_run_all_returns_every_check_in_order(factory: Factory, session: Session) -> None:
    t = factory.txn()
    d = factory.dispute()
    items = ev.run_all_checks(session, d, t, NOW)
    assert [i.check_name for i in items] == list(CheckName)
