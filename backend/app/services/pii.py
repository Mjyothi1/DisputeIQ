"""PII masking. Everything that reaches an LLM, a log line or an audit event goes through here.

Masked (regex based, best effort - see docs/SECURITY.md for the honest limits): emails, UPI IDs,
bank account numbers (keyword-anchored), Aadhaar (keyword-anchored or 4-4-4 grouped), card numbers
(13-19 digits, last four kept), Indian mobile numbers, PAN ids, CVV/CVC, OTP values (keyword-
anchored) and card expiry dates (keyword-anchored). Plain digit strings without a keyword or
grouping (order numbers, reference ids) are left alone on purpose.

Not masked: names, addresses, dates of birth, free-text descriptions of identifiers, and any
identifier written in an unusual format. Treat masking as risk reduction, not a guarantee.
"""

import re
from dataclasses import dataclass, field

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# "account number 123456789012", "a/c no: 1234567890", "acct 123..."
_ACCOUNT = re.compile(
    r"(?i)\b(account|acct|a/c)(\s*(?:number|no\.?|num|#))?\s*[:\-]?\s*(\d[\d\s-]{7,22}\d)"
)
# 13-19 digits, optionally grouped by single spaces or dashes.
_PAN = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_UPI = re.compile(r"(?<![\w.])[A-Za-z0-9._-]{2,}@[A-Za-z][A-Za-z0-9]{1,}(?![\w.@])")
_AADHAAR_KW = re.compile(r"(?i)\b(aadhaar|aadhar|adhar|uidai?)(\s*(?:number|no\.?|num|card|#))?\s*[:\-]?\s*([2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4})(?!\d)")
_AADHAAR_GROUPED = re.compile(r"(?<![\d-])[2-9]\d{3}[ -]\d{4}[ -]\d{4}(?![\d-])")
_PAN_ID = re.compile(r"(?i)(?<![A-Za-z0-9])[A-Z]{5}\d{4}[A-Z](?![A-Za-z0-9])")
_CVV = re.compile(r"(?i)\b(cvv2?|cvc2?|security\s+code)(\s*(?:is|number|no\.?|code))?\s*[:\-]?\s*(\d{3,4})(?!\d)")
_OTP = re.compile(r"(?i)\b(otp|one[- ]time[- ](?:password|pin|code)|verification\s+code|passcode)([^\d\n]{1,25}?)(\d{4,8})(?!\d)")
_OTP_REV = re.compile(r"(?i)(?<!\d)(\d{4,8})(?!\d)(\s+is\s+(?:my|the|your)\s+(?:otp|one[- ]time[- ](?:password|pin|code)|verification\s+code))")
_EXPIRY = re.compile(r"(?i)\b(exp(?:iry|iration)?(?:\s+date)?|expires?|valid\s*(?:thru|till|until|upto))(\W{1,15}?)(?:0?[1-9]|1[0-2])\s*[/-]\s*(?:\d{4}|\d{2})(?!\d)")
_PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?|0)?(?:[6-9]\d{9}|[6-9]\d{4}[\s-]\d{5})(?!\d)")


@dataclass
class MaskResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def mask_card_number(digits: str) -> str:
    """``4111 1111 1111 1234`` -> ``XXXX-XXXX-XXXX-1234`` (only the last four digits survive)."""
    only = re.sub(r"\D", "", digits)
    return f"XXXX-XXXX-XXXX-{only[-4:]}"


def mask_pii(text: str) -> MaskResult:
    """Return ``text`` with emails, account numbers, card numbers and phones masked."""
    counts = dict.fromkeys(("email", "upi", "account", "aadhaar", "card", "phone", "pan_id", "cvv", "otp", "expiry"), 0)

    def sub(pattern: re.Pattern[str], key: str, repl: str | object) -> None:
        nonlocal text
        text, n = pattern.subn(repl, text)  # type: ignore[arg-type]
        counts[key] += n

    sub(_EMAIL, "email", "[EMAIL]")
    sub(_UPI, "upi", "[UPI_ID]")
    sub(_ACCOUNT, "account", lambda m: f"{m.group(1)} [ACCOUNT]")
    sub(_AADHAAR_KW, "aadhaar", lambda m: f"{m.group(1)} [AADHAAR]")
    sub(_PAN, "card", lambda m: mask_card_number(m.group(0)))
    sub(_PHONE, "phone", "[PHONE]")
    sub(_AADHAAR_GROUPED, "aadhaar", "[AADHAAR]")
    sub(_PAN_ID, "pan_id", "[PAN_ID]")
    sub(_CVV, "cvv", lambda m: f"{m.group(1)}{m.group(2) or ''} [CVV]")
    sub(_OTP, "otp", lambda m: f"{m.group(1)}{m.group(2)}[OTP]")
    sub(_OTP_REV, "otp", lambda m: f"[OTP]{m.group(2)}")
    sub(_EXPIRY, "expiry", lambda m: f"{m.group(1)}{m.group(2)}[EXPIRY]")
    return MaskResult(text=text, counts={k: v for k, v in counts.items() if v})
