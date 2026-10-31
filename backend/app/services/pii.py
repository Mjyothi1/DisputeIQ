"""PII masking. Everything that reaches an LLM, a log line or an audit event goes through here.

Masks, in this order: emails, bank account numbers (keyword-anchored), card numbers (13-19
digits, last four kept) and phone numbers (Indian mobile formats).
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
    counts = {"email": 0, "account": 0, "card": 0, "phone": 0}

    def sub(pattern: re.Pattern[str], key: str, repl: str | object) -> None:
        nonlocal text
        text, n = pattern.subn(repl, text)  # type: ignore[arg-type]
        counts[key] += n

    sub(_EMAIL, "email", "[EMAIL]")
    sub(_ACCOUNT, "account", lambda m: f"{m.group(1)} [ACCOUNT]")
    sub(_PAN, "card", lambda m: mask_card_number(m.group(0)))
    sub(_PHONE, "phone", "[PHONE]")
    return MaskResult(text=text, counts={k: v for k, v in counts.items() if v})
