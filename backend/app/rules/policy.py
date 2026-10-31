"""Deterministic decision policy.

The policy, not the LLM, decides the action. The LLM later explains the decision and may only
*lower* its confidence. This guarantees that eligibility, deadlines and money logic stay in code.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.db.enums import Recommendation
from app.rules.config import RulesConfig, get_rules_config
from app.rules.eligibility import EligibilityResult
from app.rules.types import Blocker, CheckName, EvidenceItem, Finding

# Maximum confidence the system will claim for each situation.
CONF_RULE_REJECT = 0.90
CONF_VERIFIED_DUPLICATE = 0.95
CONF_VERIFIED_ATM = 0.92
CONF_VERIFIED_CANCELLATION = 0.90
CONF_VERIFIED_AMOUNT = 0.88
CONF_FRAUD_NO_AUTH = 0.80
CONF_FRIENDLY_FRAUD = 0.75
CONF_REFUND_NOT_PROCESSED = 0.70
CONF_UNVERIFIABLE_CLAIM = 0.60
CONF_NEED_INFO = 0.50
CONF_FREQUENT_DISPUTER_CAP = 0.60
CONF_WEAK_MATCH_CAP = 0.70
WEAK_MATCH_SCORE = 0.80


@dataclass(frozen=True)
class PolicyDecision:
    recommendation: Recommendation
    max_confidence: float
    friendly_fraud: bool = False
    frequent_disputer: bool = False
    reasons: list[str] = field(default_factory=list)


def _finding(evidence: Sequence[EvidenceItem], name: CheckName) -> Finding | None:
    for item in evidence:
        if item.check_name is name:
            return item.finding
    return None


def baseline_recommendation(
    reason_code: str,
    eligibility: EligibilityResult,
    evidence: Sequence[EvidenceItem],
    match_score: float | None = None,
) -> PolicyDecision:
    """Map (reason code, eligibility, evidence) to a recommendation and a confidence ceiling."""
    frequent = _finding(evidence, CheckName.DISPUTE_HISTORY) is Finding.POSITIVE
    reasons: list[str] = []

    def done(
        rec: Recommendation, conf: float, friendly: bool = False, why: Sequence[str] = ()
    ) -> PolicyDecision:
        notes = [*reasons, *why]
        if frequent:
            conf = min(conf, CONF_FREQUENT_DISPUTER_CAP)
            notes.append("Customer is a frequent disputer; confidence capped.")
        return PolicyDecision(rec, conf, friendly, frequent, notes)

    if Blocker.NO_TRANSACTION in eligibility.blockers:
        return done(Recommendation.NEED_MORE_INFO, CONF_NEED_INFO, why=eligibility.reasons)

    hard = {Blocker.WINDOW_EXPIRED, Blocker.ALREADY_REFUNDED, Blocker.EVIDENCE_CONTRADICTS}
    if hard & set(eligibility.blockers):
        return done(Recommendation.REJECT, CONF_RULE_REJECT, why=eligibility.reasons)
    if Blocker.EVIDENCE_MISSING in eligibility.blockers:
        return done(Recommendation.NEED_MORE_INFO, CONF_NEED_INFO, why=eligibility.reasons)

    if reason_code == "FRAUD_NOT_AUTHORISED":
        if _finding(evidence, CheckName.STRONG_AUTHENTICATION) is Finding.POSITIVE:
            return done(
                Recommendation.REJECT,
                CONF_FRIENDLY_FRAUD,
                friendly=True,
                why=["Transaction was strongly authenticated (OTP/PIN): possible friendly fraud."],
            )
        return done(Recommendation.FILE_CHARGEBACK, CONF_FRAUD_NO_AUTH)

    if reason_code == "DUPLICATE_CHARGE":
        return done(Recommendation.REFUND, CONF_VERIFIED_DUPLICATE)
    if reason_code == "ATM_CASH_NOT_DISPENSED":
        return done(Recommendation.REFUND, CONF_VERIFIED_ATM)
    if reason_code == "CANCELLED_RECURRING":
        return done(Recommendation.FILE_CHARGEBACK, CONF_VERIFIED_CANCELLATION)
    if reason_code == "INCORRECT_AMOUNT":
        return done(Recommendation.FILE_CHARGEBACK, CONF_VERIFIED_AMOUNT)
    if reason_code == "REFUND_NOT_PROCESSED":
        return done(Recommendation.FILE_CHARGEBACK, CONF_REFUND_NOT_PROCESSED)

    # GOODS_NOT_RECEIVED / NOT_AS_DESCRIBED: nothing in our systems can verify the claim.
    if match_score is not None and match_score < 0.75:
        return done(
            Recommendation.NEED_MORE_INFO,
            CONF_NEED_INFO,
            why=["Complaint is vague or the transaction match is weak."],
        )
    return done(
        Recommendation.FILE_CHARGEBACK,
        CONF_UNVERIFIABLE_CLAIM,
        why=["Claim cannot be verified from internal data; analyst review required."],
    )


def enforce_consistency(
    recommendation: Recommendation, eligibility: EligibilityResult
) -> tuple[Recommendation, list[str]]:
    """Final guard: never allow REFUND / FILE_CHARGEBACK when the case is ineligible.

    Returns the (possibly downgraded) recommendation plus notes explaining any change.
    """
    if recommendation not in (Recommendation.REFUND, Recommendation.FILE_CHARGEBACK):
        return recommendation, []
    if eligibility.eligible:
        return recommendation, []
    hard = {Blocker.WINDOW_EXPIRED, Blocker.ALREADY_REFUNDED, Blocker.EVIDENCE_CONTRADICTS}
    target = (
        Recommendation.REJECT if hard & set(eligibility.blockers) else Recommendation.NEED_MORE_INFO
    )
    note = f"Recommendation {recommendation.value} downgraded to {target.value}: " + "; ".join(
        eligibility.reasons
    )
    return target, [note]


def confidence_cap_for_match(match_score: float | None, ambiguous: bool = False) -> float:
    """Highest confidence allowed given how well the complaint matched a transaction."""
    if match_score is None or ambiguous or match_score < WEAK_MATCH_SCORE:
        return CONF_WEAK_MATCH_CAP
    return 1.0


def evidence_verdict(
    reason_code: str, item: EvidenceItem, config: RulesConfig | None = None
) -> str:
    """How one evidence item reads for the analyst, given the reason code.

    PASS = supports the claim / raises no concern, FAIL = contradicts the claim or raises a
    concern (strong authentication on a fraud claim, prior refund, frequent disputer),
    INCONCLUSIVE = not enough data, INFO = not relevant to this reason code.
    """
    cfg = config or get_rules_config()
    spec = cfg.spec(reason_code)
    name = item.check_name.value
    if item.finding is Finding.INCONCLUSIVE:
        return "INCONCLUSIVE" if name in spec.required_evidence else "INFO"
    if name in spec.required_evidence:
        return "PASS" if item.finding is Finding.POSITIVE else "FAIL"
    if name in spec.weakened_by or name == CheckName.DISPUTE_HISTORY.value:
        return "FAIL" if item.finding is Finding.POSITIVE else "PASS"
    return "INFO"
