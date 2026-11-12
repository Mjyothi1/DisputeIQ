"""Deterministic prompt-injection detection and safe wrapping for untrusted complaint text.

This is a second, code-level layer. The primary defences are structural: the model only sees the
complaint inside delimiters as data, its output is schema-validated, and the *decision* is made
by deterministic code that the complaint text cannot reach.
"""

import re
import unicodedata

_AI = r"(?:a\.?i\.?|assistant|model|llm|bot|chatbot|classifier|agent|system|gemini|claude|gpt)"
_INSTR = r"(?:instructions?|rules?|polic(?:y|ies)|prompts?|guidelines?|directives?|safeguards?|filters?)"

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # "ignore previous instructions" - but NOT "disregard my previous complaint".
    ("override_instructions", re.compile(rf"(?i)\b(ignore|disregard|forget|override|bypass|discard)\b[^.\n]{{0,40}}\b{_INSTR}\b")),
    ("system_role_claim", re.compile(r"(?i)(^|\W)(system\s*(note|message|prompt|override)|\[admin\]|admin\s*mode|developer\s*mode|sudo\b)")),
    # Addressing the model directly (customers talk to the bank, not to "the AI").
    ("addresses_model", re.compile(rf"(?i)\b(?:note|message|instruction|attention|hey|hello|dear|reminder)s?\s+(?:to|for)\s+(?:the\s+)?{_AI}\b|\b(?:ai|assistant|llm)\s*[,:]\s*(?:you|please|classify|approve|ignore|set|output)")),
    ("directive_to_model", re.compile(rf"(?i)\b(?:you\s+(?:are|must|should)\s+(?:now\s+)?(?:an?\s+)?{_AI}|act\s+as\s+(?:an?\s+)?(?:{_AI}|admin|compliance))\b")),
    ("forced_output", re.compile(r"(?i)\b(output|reply only|respond with|set|classify\s+(?:this|it)\s+as|mark\s+(?:this|it)\s+as)\b[^.\n]{0,40}\b(recommendation|confidence|route|refund|injection_suspected|duplicate_charge|fraud_not_authorised|goods_not_received|not_as_described|cancelled_recurring|incorrect_amount|refund_not_processed|atm_cash_not_dispensed)")),
    ("skip_review", re.compile(r"(?i)(?<!not\s)(?<!n't\s)(?<!never\s)\b(skip|bypass|disable|turn\s+off|without)\b[^.\n]{0,30}\b(human|manual|review|verification|fraud\s+check|eligibility|checks?)\b")),
    ("auto_approve", re.compile(r"(?i)\b(pre-?approved|auto[- ]?resolve|auto[- ]?approve|approve\s+all|without\s+(?:checking|verification|verifying))")),
    ("prompt_leak", re.compile(r"(?i)(print|reveal|show|repeat|leak)\b[^.\n]{0,30}(system\s+prompt|your\s+instructions)")),
    ("fake_markup", re.compile(r"(?i)(<\s*/?\s*(instructions?|system|complaint)\s*>|#{2,}\s*new rules|begin override|\[/?inst\])")),
    # Claims of authority a real customer would not make.
    ("authority_claim", re.compile(r"(?i)\b(?:i\s+am|i'm|this\s+is|as)\s+(?:the\s+|a\s+|an\s+|your\s+)?(?:bank\s+|branch\s+|senior\s+|chief\s+)?(?:compliance|risk|audit|fraud|security|operations|system)\s*(?:officer|manager|head|team|auditor|admin(?:istrator)?|department)\b|\b(?:authori[sz]ed|approved|cleared)\s+by\s+(?:the\s+)?(?:compliance|risk|audit|management|bank\s+manager|ceo|rbi)\b")),
    # Hinglish (romanised Hindi) instruction overrides.
    ("hinglish_override", re.compile(r"(?i)\b(?:instructions?|rules?|niyam|policy|nirdesh)\b[^.\n]{0,30}\b(?:ignore|ignor|bhool|bhul|nazar\s*andaz|nazarandaz|hata|hatao|mat\s+maan)|\b(?:pichle|pehle\s+wale|upar\s+wale|saare|sab)\s+(?:instructions?|rules?|niyam)\b|\b(?:ignore|bhool|bhul)\s+(?:kar|karo|kijiye|kardo|karna)\b[^.\n]{0,30}\b(?:instructions?|rules?|upar|pichle)")),
    ("hinglish_skip_review", re.compile(r"(?i)\bbina\s+(?:check|jaanch|verification|review|human|manual)\b|\b(?:turant|seedha|direct)\s+(?:approve|refund)\s+(?:kar|karo|kardo|kijiye)\b[^.\n]{0,30}\b(?:ai|model|system|bina)\b|\b(?:ai|model|system)\s+(?:ko|se)\s+(?:bolo|kaho|batao)\b")),
]  # fmt: skip

# Characters used to hide instructions from naive matching.
_INVISIBLE = re.compile("[\u200b-\u200f\u2060\u00ad\ufeff]")
# "i g n o r e" / "i.g.n.o.r.e" / "i-g-n-o-r-e": 4+ single letters separated by one separator.
_SPACED = re.compile(r"(?<![A-Za-z])(?:[A-Za-z][ .\-_*]){3,}[A-Za-z](?![A-Za-z])")


def _variants(text: str) -> list[str]:
    """The text as written, plus a normalised form that undoes common obfuscation."""
    norm = unicodedata.normalize("NFKC", text)
    norm = _INVISIBLE.sub("", norm)
    despaced = _SPACED.sub(lambda m: re.sub(r"[ .\-_*]", "", m.group(0)), norm)
    # Word gaps survive in the despaced form only as multiple spaces; collapse them to one.
    despaced = re.sub(r"[ \t]{2,}", " ", despaced)
    out = [text]
    for v in (norm, despaced):
        if v not in out:
            out.append(v)
    return out


def detect_injection(text: str) -> list[str]:
    """Names of the injection patterns found in ``text`` (empty list = nothing suspicious).

    Heuristic and deliberately not exhaustive: a determined attacker can evade any pattern list.
    The real protection is structural - complaint text can never set the routing, policy,
    deadline or refund amount - so a miss here does not hand an attacker a refund.
    """
    found: list[str] = []
    for variant in _variants(text):
        for name, pat in _PATTERNS:
            if name not in found and pat.search(variant):
                found.append(name)
    return found


def wrap_untrusted(text: str) -> str:
    """Wrap complaint text as clearly delimited data; neutralise any attempt to close the tag."""
    cleaned = re.sub(r"(?i)<\s*/?\s*complaint[^>]*>", "[tag removed]", text)
    return f"<complaint>\n{cleaned}\n</complaint>"
