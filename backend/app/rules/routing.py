"""Deterministic routing: auto-resolve only clear-cut, low-value, high-confidence refunds."""

from dataclasses import dataclass, field
from decimal import Decimal

from app.db.enums import Recommendation
from app.rules.config import RulesConfig, get_rules_config
from app.rules.eligibility import EligibilityResult
from app.rules.types import RouteTarget


@dataclass(frozen=True)
class RouteDecision:
    target: RouteTarget
    reasons: list[str] = field(default_factory=list)


def route(
    recommendation: Recommendation,
    confidence: float,
    amount: Decimal | None,
    reason_code: str | None,
    eligibility: EligibilityResult,
    friendly_fraud: bool = False,
    frequent_disputer: bool = False,
    injection_suspected: bool = False,
    needs_human_flag: bool = False,
    config: RulesConfig | None = None,
) -> RouteDecision:
    """Return AUTO_RESOLVE only if *every* condition holds; otherwise HUMAN_REVIEW with reasons."""
    t = (config or get_rules_config()).thresholds
    why: list[str] = []

    # Most informative reasons first (what the analyst most needs to know).
    if friendly_fraud:
        why.append("Possible friendly fraud: the transaction was strongly authenticated.")
    if injection_suspected:
        why.append("Possible prompt injection in complaint text (ignored).")
    if frequent_disputer:
        why.append("Customer is a frequent disputer.")
    if needs_human_flag:
        why.append("Pipeline flagged the case for human review (e.g. model output invalid).")
    if not eligibility.eligible:
        why.append("Case is not eligible.")
    if recommendation is not Recommendation.REFUND:
        why.append(f"Recommendation is {recommendation.value}; only REFUND can auto-resolve.")
    if reason_code not in t.auto_resolve_codes:
        why.append(f"Reason code {reason_code} is not on the auto-resolve allow-list.")
    if confidence < t.auto_confidence:
        why.append(f"Confidence {confidence:.2f} below threshold {t.auto_confidence:.2f}.")
    if amount is None:
        why.append("No matched transaction amount.")
    elif amount > Decimal(str(t.auto_max_amount_inr)):
        why.append(f"Amount exceeds auto-approve limit of INR {t.auto_max_amount_inr:,.0f}.")

    return RouteDecision(RouteTarget.HUMAN_REVIEW if why else RouteTarget.AUTO_RESOLVE, why)
