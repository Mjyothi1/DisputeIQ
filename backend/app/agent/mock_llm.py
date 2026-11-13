"""Offline, rule-based stand-in for an LLM (``LLM_PROVIDER=mock``).

It lets the whole pipeline, API, UI and evaluation run with no API key. It is a *baseline*, not a
language model: keyword/regex understanding of English and Hinglish. Real quality numbers need a
real provider. Like a careful model, it treats injection-flagged sentences as data and ignores them.

Token counts are estimates (chars / 4) and cost is priced at the default reference rate, so the
cost-per-case figures it produces are *estimates of what a real model would cost*, not billing.
"""

import difflib
import json
import re
import time
from collections.abc import Sequence
from typing import Any, TypeVar

from pydantic import BaseModel

from app.agent.llm import DEFAULT_PRICE, LLMResult
from app.agent.schemas import (
    ClaimExtraction,
    DraftedText,
    RationaleOutput,
    ReasonClassification,
)
from app.core.config import get_settings
from app.services.injection import detect_injection

T = TypeVar("T", bound=BaseModel)

_AMOUNT = re.compile(r"(?:Rs\.?|INR|₹)\s?(\d[\d,]*(?:\.\d+)?)", re.I)
_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_DATE = re.compile(r"\b(\d{1,2})\s+(" + "|".join(_MONTHS) + r")[a-z]*\b", re.I)
_LAST4 = re.compile(r"(?:card\s+(?:ending\s+)?|XXXX-XXXX-XXXX-)(\d{4})\b", re.I)
_HINGLISH = re.compile(
    r"\b(nahi|paisa|wapas|mujhe|maine|kiya|karo|kat|gaya|hui|tha|mere|baar|dilao|nikla|mangaya)\b",
    re.I,
)
_EXPECTED_CUE = re.compile(r"(bill|agreed|price|jabki)[^.]{0,20}$", re.I)

_CLAIM_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("INCORRECT_AMOUNT", re.compile(r"bill was|agreed price|overcharg|jabki bill|bill .{0,12} ka tha")),
    ("DUPLICATE_CHARGE", re.compile(r"twice|double charge|duplicate|do baar|two deductions|charged me .* double")),
    ("ATM_CASH_NOT_DISPENSED", re.compile(r"\batm\b|did not dispense|cash nahi|zero cash")),
    ("CANCELLED_RECURRING", re.compile(r"cancel")),
    ("REFUND_NOT_PROCESSED", re.compile(r"refund of|refund approve|promised a refund|refund (has|is|was)? ?not")),
    ("FRAUD_NOT_AUTHORISED", re.compile(r"did not make|didn't make|never bought|not my transaction|nahi kiya|fraud|unauthori|not authoris|maine nahi")),
    ("NOT_AS_DESCRIBED", re.compile(r"not as described|defective|description se alag|kharab|junk|different from the listing|not what i wanted")),
    ("GOODS_NOT_RECEIVED", re.compile(r"not received|never (been )?delivered|never arrived|delivery nahi|has not come|never came|did not arrive|not delivered|never come")),
]  # fmt: skip

LETTERS = {
    "REFUND": "We have reviewed your dispute about the {amount} charge by {merchant} on {txn_date} "
    "(case {case_id}). We found the charge was posted more than once or could not be completed, "
    "and a refund of the amount has been authorised. The bank will make the payment to your account "
    "separately, and it can take a few working days to appear on your statement.",
    "FILE_CHARGEBACK": "We have reviewed your dispute about the {amount} charge by {merchant} on "
    "{txn_date} (case {case_id}). We are raising a formal dispute with the merchant on your behalf; "
    "this must be filed by {deadline}. We will update you when the merchant responds.",
    "REJECT": "We have reviewed your dispute about the {amount} charge by {merchant} on {txn_date} "
    "(case {case_id}). Based on our records we are unable to raise a dispute for this charge. "
    "If you have additional information, please reply to this letter.",
    "NEED_MORE_INFO": "We are reviewing your dispute (case {case_id}) but need more details to "
    "identify the transaction. Please send the merchant name, the amount and the date of the charge.",
}


def _tokens(*parts: str) -> int:
    return max(1, sum(len(p) for p in parts) // 4)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s]


def _clean(text: str) -> str:
    """Drop sentences that look like injected instructions."""
    return " ".join(s for s in _sentences(text) if not detect_injection(s))


def _find_merchant(text: str, names: Sequence[str]) -> str | None:
    tokens = [re.sub(r"[^\w&'-]", "", t) for t in text.split()]
    lowered = text.lower()
    for name in sorted(names, key=len, reverse=True):
        if name.lower() in lowered:
            return name
    best: tuple[float, str | None] = (0.0, None)
    for name in names:
        n = len(name.split())
        for i in range(max(0, len(tokens) - n + 1)):
            window = " ".join(tokens[i : i + n]).lower()
            ratio = difflib.SequenceMatcher(None, window, name.lower()).ratio()
            if ratio > best[0]:
                best = (ratio, name)
    return best[1] if best[0] >= 0.82 else None


class MockLLM:
    """Implements the LLMClient protocol with deterministic rules."""

    def __init__(self, merchant_names: Sequence[str] = ()) -> None:
        self.model = "mock-rules-v1"
        self.merchant_names = list(merchant_names)

    def structured(
        self,
        *,
        task: str,
        system: str,
        user: str,
        schema: type[T],
        prompt_version: str,
        payload: dict[str, Any] | None = None,
    ) -> LLMResult[T]:
        start = time.perf_counter()
        handlers = {
            "extract_claim": self._extract,
            "classify_reason": self._classify,
            "write_rationale": self._rationale,
            "draft_documents": self._draft,
        }
        out = handlers[task](payload or {})
        tin, tout = _tokens(system, user), _tokens(json.dumps(out.model_dump(), default=str))
        usd = tin / 1e6 * DEFAULT_PRICE[0] + tout / 1e6 * DEFAULT_PRICE[1]
        return LLMResult(
            parsed=schema.model_validate(out.model_dump()),
            model=self.model,
            prompt_version=prompt_version,
            tokens_in=tin,
            tokens_out=tout,
            cost_inr=round(usd * get_settings().usd_inr, 6),
            latency_ms=int((time.perf_counter() - start) * 1000),
        )

    # ---- extract_claim --------------------------------------------------------------------
    def _extract(self, p: dict[str, Any]) -> ClaimExtraction:
        raw = str(p["masked_text"])
        injected = bool(detect_injection(raw))
        text = _clean(raw)
        low = text.lower()

        amounts = [(m.start(), float(m.group(1).replace(",", ""))) for m in _AMOUNT.finditer(text)]
        claimed = expected = None
        if amounts:
            claimed = amounts[0][1]
            for pos, val in amounts:
                if _EXPECTED_CUE.search(text[max(0, pos - 25) : pos]):
                    expected = val
            if expected is not None:
                others = [v for _, v in amounts if v != expected]
                claimed = others[0] if others else claimed
                if len(amounts) == 1:
                    claimed = None

        claim = next((c for c, pat in _CLAIM_RULES if pat.search(low)), "OTHER")
        date = _DATE.search(text)
        last4 = _LAST4.search(text)
        merchant = _find_merchant(text, self.merchant_names)
        summary = f"Customer reports {claim.lower().replace('_', ' ')}"
        if merchant:
            summary += f" involving {merchant}"
        if claimed:
            summary += f" for INR {claimed:,.2f}"
        return ClaimExtraction(
            claimed_amount=claimed,
            expected_amount=expected,
            approx_day=int(date.group(1)) if date else None,
            approx_month=_MONTHS.index(date.group(2).lower()[:3]) + 1 if date else None,
            approx_year=None,
            merchant_hint=merchant,
            card_last4=last4.group(1) if last4 else None,
            claim_type=claim,
            summary=summary[:300],
            language="hinglish" if _HINGLISH.search(text) else "en",
            injection_suspected=injected,
        )

    # ---- classify_reason ------------------------------------------------------------------
    def _classify(self, p: dict[str, Any]) -> ReasonClassification:
        ext, evidence, similar = p["extraction"], p["evidence"], p.get("similar", [])
        finding = {e["check_name"]: e["finding"] for e in evidence}
        code = ext.get("claim_type", "OTHER")
        if code == "OTHER":
            code = next(
                (
                    c
                    for c, chk in [
                        ("DUPLICATE_CHARGE", "duplicate_charge"),
                        ("ATM_CASH_NOT_DISPENSED", "atm_failure"),
                        ("CANCELLED_RECURRING", "subscription_cancelled"),
                    ]
                    if finding.get(chk) == "POSITIVE"
                ),
                "GOODS_NOT_RECEIVED",
            )
            conf, why = 0.4, "Claim type unclear; chose the best-supported code from evidence."
        else:
            required = {
                "DUPLICATE_CHARGE": "duplicate_charge",
                "ATM_CASH_NOT_DISPENSED": "atm_failure",
                "CANCELLED_RECURRING": "subscription_cancelled",
                "INCORRECT_AMOUNT": "amount_mismatch",
            }.get(code)
            if required:
                ok = finding.get(required) == "POSITIVE"
                conf = 0.93 if ok else 0.6
                why = f"Complaint matches {code}; evidence '{required}' is {finding.get(required)}."
            elif code == "FRAUD_NOT_AUTHORISED":
                conf, why = 0.85, "Customer denies making the transaction."
            else:
                vague = not (ext.get("merchant_hint") and ext.get("claimed_amount"))
                conf = 0.45 if vague else 0.7
                why = f"Complaint describes {code}; no system evidence can verify it."
        if ext.get("injection_suspected"):
            conf -= 0.1
            why += " Complaint contained instruction-like text, which was ignored."
        agree = sum(1 for s in similar[:3] if s.get("reason_code") == code)
        if agree >= 2:
            conf += 0.02
        return ReasonClassification(
            code=code, confidence=round(min(max(conf, 0), 0.97), 2), justification=why
        )

    # ---- write_rationale ------------------------------------------------------------------
    def _rationale(self, p: dict[str, Any]) -> RationaleOutput:
        ev = [e for e in p.get("evidence", []) if e.get("verdict") in ("PASS", "FAIL")]
        cited = [e["check_name"] for e in ev]
        parts = [f"Recommendation {p['recommendation']} for reason code {p.get('reason_code')}."]
        parts += [f"{e['check_name']} [{e['verdict']}]: {e['summary']}" for e in ev]
        parts += list(p.get("policy_notes", []))
        if p.get("friendly_fraud"):
            parts.append("Possible friendly fraud: the transaction was strongly authenticated.")
        return RationaleOutput(
            rationale=" ".join(parts)[:1500],
            confidence=min(0.97, float(p.get("classification_confidence", 0.7))),
            cited_evidence=cited,
        )

    # ---- draft_documents ------------------------------------------------------------------
    def _draft(self, p: dict[str, Any]) -> DraftedText:
        rec = p["recommendation"]
        filing = None
        if p.get("want_filing"):
            filing = (
                "Cardholder disputes the {amount} charge by {merchant} on {txn_date} "
                f"(case {{case_id}}, reason code {p.get('reason_code')}). Summary of evidence: "
                + " ".join(p.get("evidence_lines", []))
            )
        return DraftedText(letter_body=LETTERS[rec], filing_narrative=filing)
