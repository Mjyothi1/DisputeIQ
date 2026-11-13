"""What a CUSTOMER may see about their own dispute. Deliberately narrow.

Never exposed: reviewer identity or notes, evidence details, AI rationale/confidence/prompts,
injection flags, other customers' data. The customer letter is shown only when the final
decision is the one the letter was drafted for.
"""

from dataclasses import dataclass
from datetime import datetime

from app.db import models as m
from app.db.enums import DisputeStatus, Recommendation, ReviewAction

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


def _outcome(final: Recommendation) -> tuple[str, str, str]:
    if final is Recommendation.REFUND:
        return ("APPROVED", "Approved",
                "Your dispute was approved and a refund has been authorised. The credit is processed "
                "separately by the bank and may take a few working days to appear; this page does not "
                "confirm that the money has been credited.")  # fmt: skip
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
    if d.status is DisputeStatus.NEEDS_HUMAN:
        return CustomerStatus("UNDER_REVIEW", "Under review",
                              "A bank specialist is reviewing your case. No action is needed from you.", None, None)  # fmt: skip
    dec, rev = _latest_decision(d), _latest_review(d)
    if d.status is DisputeStatus.AUTO_RESOLVED and dec is not None:
        code, label, msg = _outcome(dec.recommendation)
        return CustomerStatus(code, label, msg, dec.drafted_customer_letter, dec.created_at)
    if rev is not None:
        code, label, msg = _outcome(rev.final_decision)
        letter = None
        # The drafted letter matches only when the reviewer kept the agent's decision.
        if rev.action in (ReviewAction.APPROVE, ReviewAction.EDIT) and dec is not None:
            letter = rev.edited_letter or dec.drafted_customer_letter
        return CustomerStatus(code, label, msg, letter, rev.created_at)
    return CustomerStatus(
        "UNDER_REVIEW", "Under review", "Your case is being reviewed.", None, None
    )


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
