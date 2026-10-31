"""Deterministic deadline and eligibility logic. No LLM is ever involved here."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.core.timeutil import as_utc
from app.rules.config import RulesConfig, get_rules_config
from app.rules.types import Blocker, CheckName, EvidenceItem, Finding


@dataclass(frozen=True)
class DeadlineResult:
    deadline_at: datetime
    days_remaining: int  # negative once the deadline has passed
    expired: bool


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    deadline_at: datetime | None
    days_remaining: int | None
    blockers: list[Blocker] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)

    @property
    def window_expired(self) -> bool:
        return Blocker.WINDOW_EXPIRED in self.blockers


def compute_deadline(
    reason_code: str,
    txn_time: datetime,
    as_of: datetime,
    config: RulesConfig | None = None,
) -> DeadlineResult:
    """Deadline = transaction time + the code's window; days_remaining measured at ``as_of``.

    ``days_remaining`` is a whole number of days, rounded down (so 0 means "less than a day left"
    and a negative value means the deadline has passed).
    """
    cfg = config or get_rules_config()
    deadline = as_utc(txn_time) + timedelta(days=cfg.spec(reason_code).window_days)
    delta = deadline - as_utc(as_of)
    days = delta.days  # floors toward negative infinity for timedeltas
    return DeadlineResult(
        deadline_at=deadline, days_remaining=days, expired=delta.total_seconds() < 0
    )


def _by_name(evidence: Sequence[EvidenceItem]) -> dict[str, EvidenceItem]:
    return {e.check_name.value: e for e in evidence}


def check_eligibility(
    reason_code: str,
    txn_time: datetime | None,
    evidence: Sequence[EvidenceItem],
    as_of: datetime,
    config: RulesConfig | None = None,
) -> EligibilityResult:
    """Decide whether a dispute can proceed for ``reason_code``.

    Eligible means: a transaction was matched, it is inside the dispute window, it has not already
    been fully refunded, and every evidence check the code requires came back POSITIVE.
    """
    cfg = config or get_rules_config()
    if txn_time is None:
        return EligibilityResult(
            eligible=False,
            deadline_at=None,
            days_remaining=None,
            blockers=[Blocker.NO_TRANSACTION],
            reasons=["No matching transaction was found."],
        )

    blockers: list[Blocker] = []
    reasons: list[str] = []
    missing: list[str] = []
    by_name = _by_name(evidence)

    deadline = compute_deadline(reason_code, txn_time, as_of, cfg)
    if deadline.expired:
        blockers.append(Blocker.WINDOW_EXPIRED)
        reasons.append(
            f"Dispute window of {cfg.spec(reason_code).window_days} days expired "
            f"{-deadline.days_remaining} day(s) ago."
        )

    refund = by_name.get(CheckName.REFUND_ISSUED.value)
    if (
        refund
        and refund.finding is Finding.POSITIVE
        and refund.details.get("refund_status") == "FULL"
    ):
        blockers.append(Blocker.ALREADY_REFUNDED)
        reasons.append("Transaction has already been fully refunded.")

    for required in cfg.spec(reason_code).required_evidence:
        item = by_name.get(required)
        if item is None or item.finding is Finding.INCONCLUSIVE:
            blockers.append(Blocker.EVIDENCE_MISSING)
            missing.append(required)
            reasons.append(f"Required evidence '{required}' is missing or inconclusive.")
        elif item.finding is Finding.NEGATIVE:
            blockers.append(Blocker.EVIDENCE_CONTRADICTS)
            reasons.append(f"Required evidence '{required}' not found: {item.summary}")

    return EligibilityResult(
        eligible=not blockers,
        deadline_at=deadline.deadline_at,
        days_remaining=deadline.days_remaining,
        blockers=list(dict.fromkeys(blockers)),
        reasons=reasons,
        missing_evidence=missing,
    )
