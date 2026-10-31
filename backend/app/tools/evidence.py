"""Deterministic evidence-check tools used by the agent. Pure code, no LLM, fully unit-tested."""

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import as_utc
from app.db.enums import AuthMethod, RefundStatus, SubscriptionStatus, TxnChannel, TxnStatus
from app.db.models import Dispute, Subscription, Transaction
from app.rules.config import RulesConfig, get_rules_config
from app.rules.types import CheckName, EvidenceItem, Finding


def find_duplicates(
    session: Session, txn: Transaction, config: RulesConfig | None = None
) -> EvidenceItem:
    """Same card, merchant and amount within ``duplicate_window_hours`` of ``txn``."""
    window = timedelta(hours=(config or get_rules_config()).thresholds.duplicate_window_hours)
    candidates = session.scalars(
        select(Transaction).where(
            Transaction.card_id == txn.card_id,
            Transaction.merchant_id == txn.merchant_id,
            Transaction.amount == txn.amount,
            Transaction.id != txn.id,
            Transaction.status != TxnStatus.FAILED,
        )
    ).all()
    base = as_utc(txn.txn_time)
    dupes = sorted(
        (c for c in candidates if abs(as_utc(c.txn_time) - base) <= window),
        key=lambda c: as_utc(c.txn_time),
    )
    if not dupes:
        return EvidenceItem(
            CheckName.DUPLICATE_CHARGE,
            Finding.NEGATIVE,
            "No other charge with the same card, merchant and amount in the window.",
            {"duplicate_txn_ids": [], "window_hours": window.total_seconds() / 3600},
        )
    return EvidenceItem(
        CheckName.DUPLICATE_CHARGE,
        Finding.POSITIVE,
        f"Found {len(dupes)} matching charge(s) of INR {txn.amount} within the window.",
        {
            "duplicate_txn_ids": [d.id for d in dupes],
            "duplicate_times": [as_utc(d.txn_time).isoformat() for d in dupes],
            "window_hours": window.total_seconds() / 3600,
        },
    )


def check_authentication(txn: Transaction) -> EvidenceItem:
    """POSITIVE when the transaction was strongly authenticated (OTP/3DS or PIN)."""
    strong = txn.auth_method in (AuthMethod.OTP_3DS, AuthMethod.PIN)
    return EvidenceItem(
        CheckName.STRONG_AUTHENTICATION,
        Finding.POSITIVE if strong else Finding.NEGATIVE,
        f"Authenticated with {txn.auth_method.value}."
        if strong
        else "No strong authentication (OTP/PIN) was used.",
        {"auth_method": txn.auth_method.value, "channel": txn.channel.value},
    )


def check_refund_issued(session: Session, txn: Transaction) -> EvidenceItem:
    """POSITIVE if the transaction is reversed/refunded, or a refund transaction exists."""
    refund_txns = session.scalars(
        select(Transaction).where(
            Transaction.card_id == txn.card_id,
            Transaction.merchant_id == txn.merchant_id,
            Transaction.amount == -txn.amount,
        )
    ).all()
    status = txn.refund_status
    if txn.status is TxnStatus.REVERSED and status is RefundStatus.NONE:
        status = RefundStatus.FULL
    if refund_txns and status is RefundStatus.NONE:
        status = RefundStatus.FULL
    refunded = status is not RefundStatus.NONE
    return EvidenceItem(
        CheckName.REFUND_ISSUED,
        Finding.POSITIVE if refunded else Finding.NEGATIVE,
        f"A {status.value.lower()} refund has already been issued."
        if refunded
        else "No refund or reversal found for this transaction.",
        {"refund_status": status.value, "refund_txn_ids": [r.id for r in refund_txns]},
    )


def check_subscription_cancelled(session: Session, txn: Transaction) -> EvidenceItem:
    """POSITIVE if the subscription was cancelled strictly before this charge."""
    subs = session.scalars(
        select(Subscription).where(
            Subscription.card_id == txn.card_id, Subscription.merchant_id == txn.merchant_id
        )
    ).all()
    if not subs:
        return EvidenceItem(
            CheckName.SUBSCRIPTION_CANCELLED,
            Finding.INCONCLUSIVE,
            "No subscription record exists for this card and merchant.",
        )
    cancelled = [
        s
        for s in subs
        if s.status is SubscriptionStatus.CANCELLED
        and s.cancelled_at is not None
        and as_utc(s.cancelled_at) < as_utc(txn.txn_time)
    ]
    if cancelled:
        when = as_utc(cancelled[0].cancelled_at).isoformat()  # type: ignore[arg-type]
        return EvidenceItem(
            CheckName.SUBSCRIPTION_CANCELLED,
            Finding.POSITIVE,
            f"Subscription was cancelled on {when[:10]}, before this charge.",
            {"subscription_id": cancelled[0].id, "cancelled_at": when},
        )
    return EvidenceItem(
        CheckName.SUBSCRIPTION_CANCELLED,
        Finding.NEGATIVE,
        "Subscription was active (or cancelled only after this charge).",
        {"subscription_ids": [s.id for s in subs]},
    )


def check_dispute_history(
    session: Session, dispute: Dispute, as_of: datetime, config: RulesConfig | None = None
) -> EvidenceItem:
    """POSITIVE when the customer filed >= ``frequent_disputer_count`` other disputes in a year."""
    t = (config or get_rules_config()).thresholds
    since = as_utc(as_of) - timedelta(days=t.history_lookback_days)
    others = session.scalars(
        select(Dispute).where(Dispute.customer_id == dispute.customer_id, Dispute.id != dispute.id)
    ).all()
    count = sum(1 for d in others if since <= as_utc(d.created_at) <= as_utc(as_of))
    frequent = count >= t.frequent_disputer_count
    return EvidenceItem(
        CheckName.DISPUTE_HISTORY,
        Finding.POSITIVE if frequent else Finding.NEGATIVE,
        f"Customer filed {count} other dispute(s) in the last {t.history_lookback_days} days.",
        {"prior_disputes": count, "threshold": t.frequent_disputer_count},
    )


def check_atm_failure(txn: Transaction) -> EvidenceItem:
    """POSITIVE for an ATM transaction that debited the account but did not dispense cash."""
    if txn.channel is not TxnChannel.ATM:
        return EvidenceItem(CheckName.ATM_FAILURE, Finding.NEGATIVE, "Not an ATM transaction.", {})
    dispensed = (txn.details or {}).get("cash_dispensed")
    if dispensed is None:
        return EvidenceItem(
            CheckName.ATM_FAILURE, Finding.INCONCLUSIVE, "ATM journal has no dispense result."
        )
    failed = txn.account_debited and dispensed is False
    return EvidenceItem(
        CheckName.ATM_FAILURE,
        Finding.POSITIVE if failed else Finding.NEGATIVE,
        "ATM journal shows account debited but cash not dispensed."
        if failed
        else "ATM journal shows cash was dispensed (or account not debited).",
        {"cash_dispensed": dispensed, "account_debited": txn.account_debited},
    )


def check_amount_mismatch(
    txn: Transaction, expected_amount: Decimal | None, config: RulesConfig | None = None
) -> EvidenceItem:
    """POSITIVE when the charged amount differs from the amount the customer says was agreed."""
    if expected_amount is None:
        return EvidenceItem(
            CheckName.AMOUNT_MISMATCH, Finding.INCONCLUSIVE, "Customer gave no expected amount."
        )
    diff = txn.amount - expected_amount
    mismatch = diff != 0
    return EvidenceItem(
        CheckName.AMOUNT_MISMATCH,
        Finding.POSITIVE if mismatch else Finding.NEGATIVE,
        f"Charged INR {txn.amount} vs expected INR {expected_amount} (difference INR {diff})."
        if mismatch
        else "Charged amount equals the expected amount.",
        {"charged": str(txn.amount), "expected": str(expected_amount), "difference": str(diff)},
    )


def run_all_checks(
    session: Session,
    dispute: Dispute,
    txn: Transaction,
    as_of: datetime,
    expected_amount: Decimal | None = None,
    config: RulesConfig | None = None,
) -> list[EvidenceItem]:
    """Run every evidence check for a matched transaction, in a fixed order."""
    return [
        find_duplicates(session, txn, config),
        check_authentication(txn),
        check_refund_issued(session, txn),
        check_subscription_cancelled(session, txn),
        check_dispute_history(session, dispute, as_of, config),
        check_atm_failure(txn),
        check_amount_mismatch(txn, expected_amount, config),
    ]
