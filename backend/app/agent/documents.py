"""Customer letter and chargeback filing assembly.

The LLM writes prose only, using placeholders. Every amount, date, name and id is inserted from
database values here, and model text containing literal money/dates/long numbers is rejected in
favour of a deterministic fallback, so a hallucinated figure can never reach a document.
"""

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.core.timeutil import as_utc
from app.db.enums import Recommendation
from app.rules.types import EvidenceItem

PLACEHOLDERS = ("amount", "merchant", "txn_date", "case_id", "deadline")
_MONEY = re.compile(r"(?:Rs\.?|INR|₹)\s?\d", re.I)
_LONG_NUMBER = re.compile(r"\d{4,}")
_DATE = re.compile(
    r"\b\d{1,2}[\s/-](?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{1,2})[a-z]*[\s/-]?\d{0,4}\b",
    re.I,
)
# Wording that states money has already moved. No payment/refund integration exists, so no letter
# may say this; a draft that does is rejected in favour of the template (see validate_llm_text).
COMPLETED_REFUND_CLAIM = re.compile(
    r"\b(?:has|have|had)\s+been\s+(?:credited|refunded|reversed|processed|paid|returned)\b"
    r"|\b(?:we|we've|we\s+have|i\s+have)\s+(?:now\s+)?(?:processed|credited|refunded|reversed|issued|paid)\b"
    r"|\b(?:are|is|am)\s+(?:now\s+)?(?:refunding|crediting|reversing|returning)\b"
    r"|\brefund(?:ed)?\s+(?:has|was)\s+(?:been\s+)?(?:processed|issued|credited|completed|paid)\b"
    r"|\b(?:credited|refunded|reversed|returned)\s+(?:back\s+)?(?:to|into)\s+your\b"
    r"|\brefund\s+(?:is\s+)?(?:processed|complete|completed)\b",
    re.I,
)
REFUND_AUTHORISED_SENTENCE = (
    "a refund of the amount has been authorised. The bank will make the payment to your account "
    "separately, and it can take a few working days to appear on your statement"
)
_BAD_PLACEHOLDER = re.compile(r"\{(?!(?:" + "|".join(PLACEHOLDERS) + r")\})[^}]*\}")

FALLBACK_BODY = {
    Recommendation.REFUND: "We have reviewed your dispute about the {amount} charge by {merchant} on {txn_date} (case {case_id}) and " + REFUND_AUTHORISED_SENTENCE + ".",
    Recommendation.FILE_CHARGEBACK: "We have reviewed your dispute about the {amount} charge by {merchant} on {txn_date} (case {case_id}). We are raising a formal dispute with the merchant on your behalf and will update you on the outcome.",
    Recommendation.REJECT: "We have reviewed your dispute about the {amount} charge by {merchant} on {txn_date} (case {case_id}). Based on our records we are unable to raise a dispute for this charge. If you have further information, please reply to this letter.",
    Recommendation.NEED_MORE_INFO: "We are reviewing your dispute (case {case_id}) but need more details to identify the transaction. Please send the merchant name, the amount and the date of the charge.",
}  # fmt: skip
FALLBACK_NARRATIVE = (
    "Cardholder disputes the {amount} charge by {merchant} on {txn_date} (case {case_id}). "
    "The evidence collected by the issuer is summarised above."
)


@dataclass(frozen=True)
class DocFacts:
    """Everything that is inserted into documents, straight from the database."""

    case_id: str
    customer_name: str
    merchant: str
    amount: str
    txn_date: str
    deadline: str
    received: str
    card_last4: str
    network: str
    txn_ref: str
    channel: str
    auth_method: str
    mcc: str
    has_txn: bool = True

    def placeholders(self) -> dict[str, str]:
        return {p: getattr(self, p) for p in PLACEHOLDERS}


def format_inr(amount: Decimal) -> str:
    return f"INR {amount:,.2f}"


def format_date(dt: datetime) -> str:
    return as_utc(dt).strftime("%d %b %Y")


def case_ref(dispute_id: int) -> str:
    return f"DIQ-{dispute_id:06d}"


def validate_llm_text(text: str) -> list[str]:
    """Problems that make model-written text unsafe to send (empty list = acceptable)."""
    problems = []
    if _MONEY.search(text):
        problems.append("literal amount")
    if _DATE.search(text):
        problems.append("literal date")
    if _LONG_NUMBER.search(text):
        problems.append("long number")
    if _BAD_PLACEHOLDER.search(text):
        problems.append("unknown placeholder")
    if COMPLETED_REFUND_CLAIM.search(text):
        problems.append("claims a completed refund")
    return problems


def claims_completed_refund(text: str | None) -> bool:
    """True if the text says money has already been refunded/credited."""
    return bool(text and COMPLETED_REFUND_CLAIM.search(text))


# Letters drafted before this fix used exactly these phrasings; they are corrected when displayed.
_LEGACY = (
    re.compile(r"\b(?:and\s+)?(?:we\s+)?are refunding the amount to your account", re.I),
)


def correct_legacy_refund_wording(text: str) -> str:
    """Rewrite the old template's premature claim into authorised-not-paid wording."""
    for pat in _LEGACY:
        text = pat.sub("and " + REFUND_AUTHORISED_SENTENCE, text)
    return text.replace("and and ", "and ")


def fill(text: str, facts: DocFacts) -> str:
    return text.format_map(defaultdict(str, facts.placeholders()))


def safe_body(llm_text: str | None, fallback: str, facts: DocFacts) -> tuple[str, list[str]]:
    """Return filled text, falling back to the template if the model text is unsafe."""
    llm_text = clean_body(llm_text) if llm_text else llm_text
    problems = validate_llm_text(llm_text) if llm_text else ["empty"]
    return fill(fallback if problems else str(llm_text), facts), problems


def _subject(facts: DocFacts) -> str:
    if not facts.has_txn:
        return f"Card dispute {facts.case_id}"
    return f"Card dispute {facts.case_id}: {facts.merchant}, {facts.amount}, {facts.txn_date}"


_GREETING = re.compile(r"^\s*(?:dear|hi|hello|namaste)\b[^\n]*\n+", re.I)
_SIGNOFF = re.compile(
    r"\n+\s*(?:(?:yours\s+)?(?:sincerely|faithfully|truly)|(?:kind|best|warm)?\s*regards|thank you|thanks)"
    r"\s*,?\s*(?:\n[^\n]*){0,3}\s*$",
    re.I,
)
PENDING_BODY = {
    Recommendation.REFUND: "Thank you for contacting us about the {amount} charge by {merchant} on {txn_date} (case {case_id}). Your dispute is currently under review. Our checks so far support your claim, and a refund has been recommended; it has not yet been approved. We will write to you again as soon as a decision is made. You do not need to do anything further.",
    Recommendation.FILE_CHARGEBACK: "Thank you for contacting us about the {amount} charge by {merchant} on {txn_date} (case {case_id}). Your dispute is currently under review. Our checks so far support your claim, and raising a formal dispute with the merchant has been recommended; this has not yet been approved. We will write to you again as soon as a decision is made.",
    Recommendation.REJECT: "Thank you for contacting us about the {amount} charge by {merchant} on {txn_date} (case {case_id}). Your dispute is currently under review by our team. We will write to you again as soon as a decision is made.",
    Recommendation.NEED_MORE_INFO: "Thank you for contacting us (case {case_id}). Your dispute is currently under review. To help us identify the transaction, please reply with the merchant name, the amount and the date of the charge.",
}  # fmt: skip


def clean_body(text: str) -> str:
    """Strip greetings and sign-offs a model may add: build_letter adds exactly one of each."""
    text = text.strip()
    while _GREETING.match(text):
        text = _GREETING.sub("", text, count=1).strip()
    return _SIGNOFF.sub("", text).strip()


def greeting_name(customer_name: str) -> str:
    """'Demo Customer - Meera Iyer' -> 'Meera'; 'Asha Rao' -> 'Asha'; '' -> 'Customer'."""
    person = customer_name.split(" - ", 1)[-1].strip()
    return person.split()[0] if person else "Customer"


def is_clean_letter(text: str | None) -> bool:
    """A letter that is safe to show: one greeting, no completed-payment claim."""
    if not text or claims_completed_refund(text):
        return False
    return len(re.findall(r"(?im)^\s*dear\b", text)) <= 1 and "Dear Demo," not in text


def build_letter(facts: DocFacts, body: str) -> str:
    first = greeting_name(facts.customer_name)
    body = clean_body(body)
    return (
        f"Date: {facts.received}\n"
        f"To: {facts.customer_name}\n"
        f"Re: {_subject(facts)}\n\n"
        f"Dear {first},\n\n{body.strip()}\n\n"
        "Sincerely,\nCard Disputes Team"
    )


def evidence_lines(evidence: Sequence[EvidenceItem]) -> list[str]:
    return [
        f"{e.check_name.value}: {e.summary}" for e in evidence if e.finding.value != "INCONCLUSIVE"
    ]


def build_filing(
    facts: DocFacts, reason_code: str, evidence: Sequence[EvidenceItem], narrative: str
) -> str:
    lines = "\n".join(f"  - {line}" for line in evidence_lines(evidence)) or "  - (none)"
    return (
        "CHARGEBACK FILING (DRAFT: requires analyst approval before submission)\n"
        f"Case: {facts.case_id}\n"
        f"Reason code: {reason_code}\n"
        f"Card: {facts.network} ending {facts.card_last4}\n"
        f"Merchant: {facts.merchant} (MCC {facts.mcc})\n"
        f"Transaction: {facts.txn_ref} | {facts.txn_date} | {facts.amount} | "
        f"{facts.channel} | auth {facts.auth_method}\n"
        f"Filing deadline: {facts.deadline}\n\n"
        f"Evidence summary:\n{lines}\n\n"
        f"Narrative:\n{narrative.strip()}"
    )
