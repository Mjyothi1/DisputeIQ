"""Offline complaint-text writer.

The brief asks for LLM-written complaints. This template writer is the deterministic, offline
default (reproducible, free, needs no API key). ``ComplaintWriter`` is a small protocol so an
LLM-backed writer can be dropped in (see ``data_gen/seed.py --llm``).
"""

import hashlib
import json
import os
import random
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel

STYLES = ["formal", "angry", "short", "hinglish", "typos", "wrong_spelling", "wrong_date"]


@dataclass
class ComplaintContext:
    """Facts a complaint may mention. ``None`` means the customer does not mention it."""

    reason_code: str
    merchant: str | None
    amount: str | None  # already formatted, e.g. "Rs 1,499"
    date: str | None  # e.g. "12 Oct"
    last4: str | None
    expected_amount: str | None = None
    vague: bool = False
    full_pan: str | None = None
    phone: str | None = None
    email: str | None = None
    style: str = "formal"
    injection: str | None = None


class ComplaintWriter(Protocol):
    def write(self, rng: random.Random, ctx: ComplaintContext, style: str) -> str: ...


# {m}=merchant {a}=amount {d}=date {c}=card last4 {e}=expected amount
BASE: dict[str, dict[str, str]] = {
    "DUPLICATE_CHARGE": {
        "formal": "I was charged {a} twice by {m} on {d} for a single purchase on my card ending {c}. Kindly reverse the duplicate charge.",
        "angry": "{m} has charged me {a} TWICE on {d}! Same order, two deductions from card {c}. Fix this right now!",
        "short": "double charge {a} {m} {d}",
        "hinglish": "Mere card {c} se {m} ne {d} ko {a} do baar kaat liye hain. Ek order tha, please extra paisa wapas karo.",
    },
    "FRAUD_NOT_AUTHORISED": {
        "formal": "I did not make or authorise the transaction of {a} at {m} on {d} on my card ending {c}. Please investigate and reverse it.",
        "angry": "Who is {m}?? I never bought anything there. {a} gone from my card {c} on {d}. This is fraud, get my money back!",
        "short": "not my transaction {a} {m} {d}",
        "hinglish": "Yeh {a} ka transaction {m} pe {d} ko maine nahi kiya. Card {c} se paisa kat gaya, mujhe fraud lag raha hai.",
    },
    "GOODS_NOT_RECEIVED": {
        "formal": "I paid {a} to {m} on {d} for an order that has never been delivered. Despite several follow-ups I have received nothing.",
        "angry": "Paid {a} to {m} on {d} and the product NEVER arrived. Support keeps ignoring me. Refund me!",
        "short": "item not received {m} {a}",
        "hinglish": "Maine {m} se {d} ko {a} ka order kiya tha, abhi tak delivery nahi hui. Please paisa wapas dilao.",
    },
    "NOT_AS_DESCRIBED": {
        "formal": "The item I bought from {m} on {d} for {a} is materially different from the listing and partly defective. The merchant refuses a return.",
        "angry": "{m} sent me junk! Listing said one thing, I got another. {a} on {d}. They won't take it back!",
        "short": "product defective not as described {m} {a}",
        "hinglish": "{m} se {d} ko {a} ka saman mangaya, jo aaya woh description se alag aur kharab hai. Return nahi le rahe.",
    },
    "CANCELLED_RECURRING": {
        "formal": "I cancelled my subscription with {m} before the billing date, yet {a} was charged to my card ending {c} on {d}.",
        "angry": "I CANCELLED {m} weeks ago and they still billed me {a} on {d}! Stop stealing my money!",
        "short": "charged {a} by {m} after cancelling subscription",
        "hinglish": "Maine {m} ka subscription cancel kar diya tha phir bhi {d} ko {a} kat gaye. Wapas karo.",
    },
    "INCORRECT_AMOUNT": {
        "formal": "{m} charged my card {a} on {d}, whereas the agreed price was {e}. Please correct the amount.",
        "angry": "The bill was {e} but {m} charged {a} on {d}. Overcharged! Sort it out.",
        "short": "charged {a} but bill was {e} at {m}",
        "hinglish": "{m} ne {d} ko {a} charge kiya jabki bill {e} ka tha. Extra amount wapas chahiye.",
    },
    "REFUND_NOT_PROCESSED": {
        "formal": "{m} confirmed a refund of {a} for my purchase on {d}, but the amount has not been credited to my account.",
        "angry": "{m} promised a refund of {a} ages ago ({d}) and I still have not got a single rupee back!",
        "short": "refund of {a} from {m} not received",
        "hinglish": "{m} ne {d} wale {a} ka refund approve kiya tha par paisa abhi tak account me nahi aaya.",
    },
    "ATM_CASH_NOT_DISPENSED": {
        "formal": "I attempted to withdraw {a} at {m} on {d}. The machine did not dispense cash but my account was debited.",
        "angry": "{m} swallowed my transaction! {a} debited on {d} and zero cash came out. Reverse it!",
        "short": "atm no cash but debited {a} {m} {d}",
        "hinglish": "{m} se {d} ko {a} nikalne ki koshish ki, cash nahi nikla lekin account se paisa kat gaya.",
    },
}

VAGUE: dict[str, str] = {
    "GOODS_NOT_RECEIVED": "I ordered something from {m} a while back and it still has not come. Please look into it.",
    "NOT_AS_DESCRIBED": "What I got from {m} is not what I wanted. Not happy, please help.",
}
VAGUE_NO_MERCHANT = "Something I paid for online never arrived. Need my money back."

_SWAPS = {"a": "e", "e": "a", "o": "u", "i": "e"}


def misspell(rng: random.Random, word: str) -> str:
    """Introduce one realistic spelling error."""
    if len(word) < 4:
        return word
    i = rng.randrange(1, len(word) - 1)
    kind = rng.choice(["drop", "swap", "double"])
    if kind == "drop":
        return word[:i] + word[i + 1 :]
    if kind == "swap":
        return word[:i] + word[i + 1] + word[i] + word[i + 2 :]
    return word[:i] + word[i] + word[i:]


def add_typos(rng: random.Random, text: str) -> str:
    """Sprinkle typos over roughly one word in six."""
    out = []
    for w in text.split():
        if len(w) > 4 and rng.random() < 0.17 and w.isalpha():
            w = misspell(rng, w)
        out.append(w)
    return " ".join(out)


def pii_extras(ctx: ComplaintContext) -> str:
    """Sentences carrying planted PII (card number, phone, email), with a leading space."""
    parts = []
    if ctx.full_pan:
        parts.append(f"My card number is {ctx.full_pan}.")
    if ctx.phone:
        parts.append(f"You can call me on {ctx.phone}.")
    if ctx.email:
        parts.append(f"Email: {ctx.email}")
    return "".join(" " + x for x in parts)


class TemplateWriter:
    """Deterministic complaint writer used by default."""

    def write(self, rng: random.Random, ctx: ComplaintContext, style: str) -> str:
        fmt = {
            "m": ctx.merchant or "the merchant",
            "a": ctx.amount or "the amount",
            "d": ctx.date or "recently",
            "c": ctx.last4 or "on file",
            "e": ctx.expected_amount or "the agreed price",
        }
        if ctx.vague:
            text = (
                VAGUE[ctx.reason_code].format(**fmt)
                if ctx.merchant and ctx.reason_code in VAGUE
                else VAGUE_NO_MERCHANT
            )
        else:
            variants = BASE[ctx.reason_code]
            base_style = style if style in variants else rng.choice(["formal", "angry"])
            text = variants[base_style].format(**fmt)
            if style == "typos":
                text = add_typos(rng, text)
        return text + pii_extras(ctx)


# --------------------------------------------------------------------------------------------
# LLM-backed writer (used with ``python -m data_gen.seed --llm``)
# --------------------------------------------------------------------------------------------

STYLE_BRIEFS = {
    "formal": "formal and polite, full sentences",
    "angry": "angry and frustrated, some capital letters and exclamation marks",
    "short": "very short and terse, like a quick chat message",
    "hinglish": "Hinglish: Hindi written in Roman script mixed with English, casual",
    "typos": "casual with several realistic spelling mistakes and typos",
    "wrong_spelling": "casual, with the merchant name slightly misspelled",
    "wrong_date": "casual and a little unsure about exact details",
}


class _ComplaintText(BaseModel):
    text: str


def _required_facts(ctx: "ComplaintContext", style: str) -> list[str]:
    """Strings the written complaint must contain verbatim (checked case-insensitively)."""
    if ctx.vague:
        return []
    out = [ctx.amount, ctx.expected_amount, ctx.last4]
    if style != "wrong_spelling":
        out.append(ctx.merchant)
    return [x for x in out if x]


class LLMWriter:
    """Writes complaints with an LLM, falling back to the template writer.

    The template writer always runs first so the random stream (and therefore every other part of
    the dataset) is identical regardless of provider. The LLM text is accepted only if it
    contains every fact the scenario needs; otherwise one retry, then the template text is used.
    Results are cached on disk so reseeding is cheap and reproducible.
    """

    SYSTEM = (
        "You write realistic customer complaint messages to a bank about a disputed card "
        "transaction, for a synthetic test dataset. Return only the message text. Keep every "
        "provided fact exactly as given (amounts, merchant, card digits). Do not invent other "
        "numbers, names or dates. Do not add greetings with names or signatures."
    )

    def __init__(self, llm: Any, cache_path: str | None = None) -> None:
        self.llm: Any = llm
        self.fallback = TemplateWriter()
        self.cache_path = cache_path
        self.cache: dict[str, str] = {}
        self.stats = {"llm": 0, "cached": 0, "fallback": 0}
        if cache_path and os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                self.cache = json.load(f)

    def _prompt(self, ctx: ComplaintContext, style: str) -> str:
        facts = {
            "merchant": ctx.merchant if style != "wrong_spelling" else None,
            "merchant_note": "misspell the merchant name slightly"
            if style == "wrong_spelling"
            else None,
            "amount": ctx.amount,
            "expected_amount": ctx.expected_amount,
            "date": ctx.date if style != "wrong_date" else "(say you are not sure of the date)",
            "card_last4": ctx.last4,
        }
        facts = {k: v for k, v in facts.items() if v}
        if ctx.vague:
            problem = "Be vague: do NOT mention amount, date or card digits."
        else:
            problem = "Mention the amount, merchant and card digits where natural."
        return (
            f"Problem type: {ctx.reason_code.replace('_', ' ').lower()}.\n"
            f"Tone/style: {STYLE_BRIEFS.get(style, 'plain')}.\n"
            f"Facts: {json.dumps(facts, ensure_ascii=False)}\n{problem}\n"
            "Write 1-3 sentences."
        )

    @staticmethod
    def _valid(text: str, ctx: ComplaintContext, style: str) -> bool:
        low = text.lower()
        if not 10 <= len(text) <= 700:
            return False
        if ctx.vague and ctx.amount and ctx.amount.lower() in low:
            return False
        return all(f.lower() in low for f in _required_facts(ctx, style))

    def write(self, rng: random.Random, ctx: ComplaintContext, style: str) -> str:
        template_text: str = self.fallback.write(rng, ctx, style)
        extras = pii_extras(ctx)
        prompt = self._prompt(ctx, style)
        key = hashlib.sha256(f"{self.llm.model}|{prompt}".encode()).hexdigest()
        if key in self.cache:
            self.stats["cached"] += 1
            return self.cache[key] + extras
        for _ in range(2):
            try:
                res = self.llm.structured(
                    task="write_complaint",
                    system=self.SYSTEM,
                    user=prompt,
                    schema=_ComplaintText,
                    prompt_version="data-v1",
                )
            except Exception:  # LLMError or anything the SDK raises; never abort seeding
                break
            text: str = str(res.parsed.text).strip()
            if self._valid(text, ctx, style):
                self.stats["llm"] += 1
                self.cache[key] = text
                self._save()
                return text + extras
        self.stats["fallback"] += 1
        return template_text

    def _save(self) -> None:
        if self.cache_path:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False)
