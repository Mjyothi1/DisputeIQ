"""Plain typed values exchanged between evidence tools, rules engine and agent."""

import sys
from dataclasses import dataclass, field
from typing import Any

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        """Backport of StrEnum for Python 3.10."""

        def __str__(self) -> str:
            return self.value


class Finding(StrEnum):
    """Neutral outcome of an evidence check (interpretation depends on the reason code)."""

    POSITIVE = "POSITIVE"  # the condition the check looks for is present
    NEGATIVE = "NEGATIVE"  # looked for it and it is absent
    INCONCLUSIVE = "INCONCLUSIVE"  # not enough data to say


class CheckName(StrEnum):
    DUPLICATE_CHARGE = "duplicate_charge"
    STRONG_AUTHENTICATION = "strong_authentication"
    REFUND_ISSUED = "refund_issued"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    DISPUTE_HISTORY = "dispute_history"
    ATM_FAILURE = "atm_failure"
    AMOUNT_MISMATCH = "amount_mismatch"


class Blocker(StrEnum):
    """Why a dispute is not eligible."""

    NO_TRANSACTION = "NO_TRANSACTION"
    WINDOW_EXPIRED = "WINDOW_EXPIRED"
    ALREADY_REFUNDED = "ALREADY_REFUNDED"
    EVIDENCE_CONTRADICTS = "EVIDENCE_CONTRADICTS"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"


@dataclass(frozen=True)
class EvidenceItem:
    """Result of one deterministic evidence check."""

    check_name: CheckName
    finding: Finding
    summary: str
    details: dict[str, Any] = field(default_factory=dict)


class RouteTarget(StrEnum):
    AUTO_RESOLVE = "AUTO_RESOLVE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
