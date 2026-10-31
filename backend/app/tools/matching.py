"""Deterministic transaction matching: amount tolerance + fuzzy merchant + date window.

Score = 0.45*amount + 0.35*merchant + 0.20*date. A signal the customer did not provide scores 0,
so vague complaints can never reach a high score (a built-in coverage penalty).
"""

import difflib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.timeutil import as_utc
from app.db.models import Card, Transaction
from app.rules.config import RulesConfig, get_rules_config

W_AMOUNT, W_MERCHANT, W_DATE = 0.45, 0.35, 0.20
LOOKBACK_DAYS = 400
TIE_EPSILON = 0.05


@dataclass(frozen=True)
class ClaimFacts:
    """The subset of the extracted claim that matching needs (already validated)."""

    claimed_amount: float | None = None
    merchant_hint: str | None = None
    approx_day: int | None = None
    approx_month: int | None = None
    approx_year: int | None = None
    card_last4: str | None = None


@dataclass
class MatchResult:
    txn: Transaction | None
    score: float
    ambiguous: bool = False
    candidates: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def resolve_date(
    day: int | None, month: int | None, year: int | None, as_of: datetime
) -> date | None:
    """Turn day/month(/year) into a date. Without a year, use the latest such date not after
    ``as_of`` (+1 day of slack). Returns None for missing or impossible dates."""
    if day is None or month is None:
        return None
    limit = (as_utc(as_of) + timedelta(days=1)).date()
    years = [year] if year else [limit.year, limit.year - 1]
    for y in years:
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        if d <= limit or year:
            return d
    return None


def _merchant_score(hint: str | None, name: str) -> float:
    if not hint:
        return 0.0
    h, n = hint.lower().strip(), name.lower().strip()
    ratio = difflib.SequenceMatcher(None, h, n).ratio()
    if h in n or n in h:
        ratio = max(ratio, 0.9)
    return ratio if ratio >= 0.6 else 0.0


def _amount_score(claimed: float | None, actual: float, tol_pct: float) -> float:
    if claimed is None:
        return 0.0
    if abs(claimed - actual) <= 1.0:  # whole-rupee rounding in complaints
        return 1.0
    pct = abs(claimed - actual) / actual * 100 if actual else 100.0
    return 0.8 * (1 - pct / tol_pct) if pct <= tol_pct else 0.0


def _date_score(target: date | None, txn_time: datetime, window_days: int) -> float:
    if target is None:
        return 0.0
    delta = abs((as_utc(txn_time).date() - target).days)
    return 1 - delta / window_days if delta <= window_days else 0.0


def match_transaction(
    session: Session,
    customer_id: int,
    facts: ClaimFacts,
    as_of: datetime,
    config: RulesConfig | None = None,
) -> MatchResult:
    """Find the customer's transaction the complaint most likely refers to."""
    t = (config or get_rules_config()).thresholds
    since = as_utc(as_of) - timedelta(days=LOOKBACK_DAYS)
    until = as_utc(as_of) + timedelta(days=1)

    cards = session.scalars(select(Card).where(Card.customer_id == customer_id)).all()
    notes: list[str] = []
    if facts.card_last4:
        narrowed = [c for c in cards if c.last4 == facts.card_last4]
        if narrowed:
            cards = narrowed
            notes.append(f"Restricted to card ending {facts.card_last4}.")
    if not cards:
        return MatchResult(None, 0.0, notes=[*notes, "Customer has no cards on file."])

    txns = session.scalars(
        select(Transaction)
        .options(joinedload(Transaction.merchant))
        .where(
            Transaction.card_id.in_([c.id for c in cards]),
            Transaction.amount > 0,
            Transaction.txn_time >= since,
            Transaction.txn_time <= until,
        )
    ).all()

    target = resolve_date(facts.approx_day, facts.approx_month, facts.approx_year, as_of)
    scored: list[tuple[float, datetime, Transaction, dict[str, float]]] = []
    for txn in txns:
        parts = {
            "amount": _amount_score(
                facts.claimed_amount, float(txn.amount), t.amount_tolerance_pct
            ),
            "merchant": _merchant_score(facts.merchant_hint, txn.merchant.name),
            "date": _date_score(target, txn.txn_time, t.match_window_days),
        }
        score = W_AMOUNT * parts["amount"] + W_MERCHANT * parts["merchant"] + W_DATE * parts["date"]
        scored.append((score, as_utc(txn.txn_time), txn, parts))

    # Highest score wins; on a tie the most recent transaction (the duplicate, not the original).
    scored.sort(key=lambda s: (round(s[0], 6), s[1]), reverse=True)
    top = [
        {
            "txn_id": x.id,
            "merchant": x.merchant.name,
            "amount": str(x.amount),
            "score": round(s, 3),
            **{f"{k}_score": round(v, 2) for k, v in p.items()},
        }
        for s, _, x, p in scored[:3]
    ]
    if not scored or scored[0][0] < t.min_match_score:
        best = round(scored[0][0], 3) if scored else 0.0
        return MatchResult(
            None,
            best,
            candidates=top,
            notes=[*notes, "No transaction scored above the match threshold."],
        )

    best_score, _, best_txn, _ = scored[0]
    ambiguous = False
    if len(scored) > 1:
        s2, _, t2, _ = scored[1]
        distinct = (t2.merchant_id, t2.amount) != (best_txn.merchant_id, best_txn.amount)
        if best_score - s2 <= TIE_EPSILON and distinct:
            ambiguous = True
            notes.append("Several different transactions fit the complaint equally well.")
    return MatchResult(best_txn, round(best_score, 3), ambiguous, top, notes)
