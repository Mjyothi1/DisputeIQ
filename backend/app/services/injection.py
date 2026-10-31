"""Deterministic prompt-injection detection and safe wrapping for untrusted complaint text.

This is a second, code-level layer. The primary defences are structural: the model only sees the
complaint inside delimiters as data, its output is schema-validated, and the *decision* is made
by deterministic code that the complaint text cannot reach.
"""

import re

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("override_instructions", re.compile(r"(?i)\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(instruction|rule|polic|previous|above|prompt)")),
    ("system_role_claim", re.compile(r"(?i)(^|\W)(system\s*(note|message|prompt)|\[admin\]|admin\s*mode|developer\s*mode)")),
    ("directive_to_model", re.compile(r"(?i)\b(you (are|must)|act as|assistant,)\b[^.\n]{0,60}\b(approve|refund|compliance|admin|ignore)")),
    ("forced_output", re.compile(r"(?i)\b(output|reply only|respond with|set)\b[^.\n]{0,40}\b(recommendation|confidence|route|refund|injection_suspected)")),
    ("skip_review", re.compile(r"(?i)\b(skip|bypass|disable|no)\b[^.\n]{0,30}\b(human|review|verification|fraud check|eligibility)")),
    ("auto_approve", re.compile(r"(?i)\b(pre-?approved|auto[- ]?resolve|approve all|without (checking|verification))")),
    ("prompt_leak", re.compile(r"(?i)(print|reveal|show)\b[^.\n]{0,30}system prompt")),
    ("fake_markup", re.compile(r"(?i)(<\s*/?\s*(instructions?|system|complaint)\s*>|#{2,}\s*new rules|begin override)")),
]  # fmt: skip


def detect_injection(text: str) -> list[str]:
    """Names of the injection patterns found in ``text`` (empty list = nothing suspicious)."""
    return [name for name, pat in _PATTERNS if pat.search(text)]


def wrap_untrusted(text: str) -> str:
    """Wrap complaint text as clearly delimited data; neutralise any attempt to close the tag."""
    cleaned = re.sub(r"(?i)<\s*/?\s*complaint[^>]*>", "[tag removed]", text)
    return f"<complaint>\n{cleaned}\n</complaint>"
