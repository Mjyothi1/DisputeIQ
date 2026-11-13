"""What a CUSTOMER may see about their own dispute. Deliberately narrow.

Never exposed: reviewer identity or notes, evidence details, AI rationale/confidence/prompts,
injection flags, other customers' data. The customer letter is shown only when the final
decision is the one the letter was drafted for.
"""

from dataclasses import dataclass
from datetime import datetime

from app.agent.documents import claims_completed_refund, correct_legacy_refund_wording
from app.db import models as m
from app.db.enums import DisputeStatus, Recommendation
from app.services.letters import customer_letter

CATEGORIES: dict[str, str] = {
    "CHARGED_TWICE": "Charged twice",
    "NOT_MY_TRANSACTION": "I did not make this transaction",
    "ATM_NO_CASH": "ATM did not give cash",
    "NOT_RECEIVED": "Goods or service not received",
    "WRONG_AMOUNT": "Charged the wrong amount",
    "SUBSCRIPTION_CANCELLED": "Cancelled subscription still charged",
    "REFUND_NOT_RECEIVED": "Refund not received",
    "OTHER": "Something else",
}

_FINAL = (
    DisputeStatus.AUTO_RESOLVED,
    DisputeStatus.APPROVED,
    DisputeStatus.OVERRIDDEN,
    DisputeStatus.REJECTED,
)


@dataclass
class CustomerStatus:
    code: str  # SUBMITTED | PROCESSING | UNDER_REVIEW | APPROVED | REJECTED | MORE_INFO
    label: str
    message: str
    letter: str | None
    decided_at: datetime | None


def _latest_decision(d: m.Dispute) -> m.Decision | None:
    return max(d.decisions, key=lambda x: x.id) if d.decisions else None


def _latest_review(d: m.Dispute) -> m.Review | None:
    return max(d.reviews, key=lambda x: x.id) if d.reviews else None


# There is no payment/refund integration, so no record ever confirms that money reached the customer.
# Until one exists, an approved refund is only ever described as AUTHORISED.
PAYMENT_CONFIRMATION_AVAILABLE = False

UNDER_REVIEW_SUPPORTED = (
    "Your dispute is currently under review. Our team has identified evidence supporting your "
    "claim and is evaluating the appropriate resolution."
)
UNDER_REVIEW_GENERIC = (
    "Your dispute is currently under review by our team. No action is needed from you right now."
)
REFUND_AUTHORISED = (
    "Your dispute was approved and a refund has been authorised. The bank makes the payment to "
    "your account separately; it can take a few working days to appear on your statement."
)


def _outcome(final: Recommendation) -> tuple[str, str, str]:
    if final is Recommendation.REFUND:
        return ("APPROVED", "Refund authorised", REFUND_AUTHORISED)
    if final is Recommendation.FILE_CHARGEBACK:
        return ("APPROVED", "Approved",
                "Your dispute was accepted and the bank is raising a chargeback with the merchant's bank. "
                "We will update you when the card network responds.")  # fmt: skip
    if final is Recommendation.NEED_MORE_INFO:
        return ("MORE_INFO", "More information required",
                "We need more information to continue. The bank will contact you through your "
                "registered channel.")  # fmt: skip
    return ("REJECTED", "Rejected",
            "After review, the bank could not uphold this dispute. Please see the letter below for the reasons.")  # fmt: skip


def customer_status(d: m.Dispute) -> CustomerStatus:
    if d.status is DisputeStatus.NEW:
        return CustomerStatus(
            "SUBMITTED", "Submitted", "We have received your complaint.", None, None
        )
    if d.status is DisputeStatus.PROCESSING:
        return CustomerStatus("PROCESSING", "Processing",
                              "We are checking your transaction records.", None, None)  # fmt: skip
    dec, rev = _latest_decision(d), _latest_review(d)
    if d.status is DisputeStatus.NEEDS_HUMAN:
        # A recommendation is not a decision: never reveal it as an outcome, and never say "approved".
        supported = dec is not None and dec.recommendation in (
            Recommendation.REFUND, Recommendation.FILE_CHARGEBACK,
        )  # fmt: skip
        msg = UNDER_REVIEW_SUPPORTED if supported else UNDER_REVIEW_GENERIC
        return CustomerStatus("UNDER_REVIEW", "Under review", msg, None, None)
    if d.status is DisputeStatus.AUTO_RESOLVED and dec is not None:
        code, label, msg = _outcome(dec.recommendation)
        return CustomerStatus(code, label, msg, customer_letter(d, dec), dec.created_at)
    if rev is not None:
        code, label, msg = _outcome(rev.final_decision)
        # Built for the reviewer's FINAL decision (also after an override), never the agent's draft.
        return CustomerStatus(code, label, msg, customer_letter(d, dec), rev.created_at)
    return CustomerStatus(
        "UNDER_REVIEW", "Under review", "Your case is being reviewed.", None, None
    )


def safe_letter(text: str | None) -> str | None:
    """Letter as the customer may see it: legacy premature wording corrected; anything that still
    claims a completed payment (e.g. a reviewer's edit) is withheld rather than shown."""
    if not text:
        return None
    text = correct_legacy_refund_wording(text)
    if claims_completed_refund(text) and not PAYMENT_CONFIRMATION_AVAILABLE:
        return None
    return text


def timeline(d: m.Dispute) -> list[dict[str, object]]:
    """Customer-facing milestones only (no internal steps, actors or notes)."""
    out: list[dict[str, object]] = [{"label": "Complaint submitted", "at": d.created_at}]
    st = customer_status(d)
    if d.status is not DisputeStatus.NEW:
        first_step = min((e.timestamp for e in d.audit_events), default=None)
        out.append({"label": "Transaction records checked", "at": first_step})
    if d.status is DisputeStatus.NEEDS_HUMAN or d.reviews:
        route = next(
            (e.timestamp for e in sorted(d.audit_events, key=lambda e: e.id) if e.step == "route"),
            None,
        )
        out.append({"label": "Assigned to a bank specialist", "at": route})
    if d.status in _FINAL:
        out.append({"label": f"Decision: {st.label}", "at": st.decided_at})
    return out
