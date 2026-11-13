"""The single place that decides which customer letter is shown, for reviewers and customers.

Rules (there is no payment integration, so no letter ever says money moved):
* Case pending (NEW / PROCESSING / NEEDS_HUMAN): the *pending* letter. It says the case is under
  review and that a refund (or chargeback) is only recommended, not approved.
* Auto-resolved: the stored letter if it is clean, otherwise the deterministic final letter.
* Reviewed: APPROVE / OVERRIDE / REJECT get the deterministic final letter for the reviewer's final
  decision ("refund authorised; the bank makes the payment separately"); EDIT gets the reviewer's text
  if clean, otherwise the final letter.

Letters are rebuilt from database facts, so old stored drafts (including model-written ones that
claimed "we have processed a refund") are never displayed. Stored rows are not modified.
"""

from app.agent import documents as docs
from app.db import models as m
from app.db.enums import DisputeStatus, Recommendation, ReviewAction

PENDING = (DisputeStatus.NEW, DisputeStatus.PROCESSING, DisputeStatus.NEEDS_HUMAN)


def facts_for(d: m.Dispute) -> docs.DocFacts:
    t = d.matched_txn or d.customer_txn
    tbc = "(to be confirmed)"
    return docs.DocFacts(
        case_id=docs.case_ref(d.id), customer_name=d.customer.name if d.customer else "",
        merchant=t.merchant.name if t else tbc, amount=docs.format_inr(t.amount) if t else tbc,
        txn_date=docs.format_date(t.txn_time) if t else tbc,
        deadline=docs.format_date(d.deadline_at) if d.deadline_at else "N/A",
        received=docs.format_date(d.created_at), card_last4=t.card.last4 if t else "----",
        network=t.card.network.value if t else "-", txn_ref=f"TXN-{t.id}" if t else "-",
        channel=t.channel.value if t else "-", auth_method=t.auth_method.value if t else "-",
        mcc=t.merchant.mcc if t else "-", has_txn=t is not None,
    )  # fmt: skip


def pending_letter(facts: docs.DocFacts, rec: Recommendation) -> str:
    return docs.build_letter(facts, docs.fill(docs.PENDING_BODY[rec], facts))


def final_letter(facts: docs.DocFacts, final: Recommendation) -> str:
    return docs.build_letter(facts, docs.fill(docs.FALLBACK_BODY[final], facts))


def _latest(items: list) -> object | None:  # type: ignore[type-arg]
    return max(items, key=lambda x: x.id) if items else None


def reviewer_letter(d: m.Dispute, dec: m.Decision | None) -> str | None:
    """The letter for the case's current state, as shown in the reviewer portal."""
    if dec is None:
        return None
    facts = facts_for(d)
    if d.status in PENDING:
        return pending_letter(facts, dec.recommendation)
    rev = _latest(list(d.reviews))
    if rev is None:  # auto-resolved
        stored = docs.correct_legacy_refund_wording(dec.drafted_customer_letter or "")
        return stored if docs.is_clean_letter(stored) else final_letter(facts, dec.recommendation)
    assert isinstance(rev, m.Review)
    if rev.action is ReviewAction.EDIT and docs.is_clean_letter(rev.edited_letter):
        return rev.edited_letter
    return final_letter(facts, rev.final_decision)


def letter_on_approval(d: m.Dispute, dec: m.Decision | None) -> str | None:
    """For a pending case: what the customer would receive if the reviewer approves as recommended."""
    if dec is None or d.status not in PENDING:
        return None
    return final_letter(facts_for(d), dec.recommendation)


def customer_letter(d: m.Dispute, dec: m.Decision | None) -> str | None:
    """Customers only ever get a letter once there is a decision; pending cases get none."""
    if d.status in PENDING:
        return None
    text = reviewer_letter(d, dec)
    return text if docs.is_clean_letter(text) else None
